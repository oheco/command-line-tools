#!/usr/bin/env python3
"""Install the unchanged public archive in an isolated native root and verify it."""
import argparse
import functools
import http.server
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import threading
import time

parser=argparse.ArgumentParser()
parser.add_argument('--oo',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--preview',type=Path)
parser.add_argument('--archive',type=Path,help='Seed the download cache; oo verifies size and SHA-256 before use')
parser.add_argument('--pnpm-archive',type=Path,required=True,help='Pinned pnpm 10.28.2 archive verified against npm registry integrity')
parser.add_argument('--index',default='https://oheco.org/index/v6/index.json')
args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=True)
result={'status':'running','platform':'ohos-arm64','phase':'preview' if args.preview else 'formal','steps':[],'user_configuration_modified':False}
server=None

def save():
    (args.output/'install-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')

def run(label,command,env,cwd,timeout=120):
    print(label,flush=True)
    with (args.output/(label+'.log')).open('w') as log:
        process=subprocess.Popen([str(v) for v in command],env=env,cwd=cwd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:code=process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
            raise RuntimeError(label+' timed out')
    result['steps'].append({'label':label,'exit_code':code})
    save()
    print('exit:',code,flush=True)
    if code:raise RuntimeError(label+' failed; see saved log')

private_parent=Path(os.environ['TMPDIR']).resolve(strict=True)
try:
    if args.preview:
        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*_):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(args.preview)))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        args.index=f'http://127.0.0.1:{server.server_port}/index/v6/index.json'
    with tempfile.TemporaryDirectory(prefix='command-line-tools-install-',dir=private_parent) as temporary:
        private=Path(temporary).resolve();assert private.parent==private_parent and private.name.startswith('command-line-tools-install-')
        root=private/"root with spaces";root.mkdir()
        if args.archive:
            cached=root/'cache/downloads/60929c00ae486cc038ea48145497ad34dbd4ac6a25c3f2fa895ce74afb4607f5.tar.gz'
            cached.parent.mkdir(parents=True)
            assert cached.resolve().is_relative_to(private) and not cached.exists()
            shutil.copyfile(args.archive,cached)
            result['verified_archive_seeded']=True
        env=dict(os.environ)
        env.update(OHECO_ROOT=str(root),OHECO_INDEX_URL=args.index,OHECO_NO_AUTO_UPDATE='1',HTTP_PROXY='socks5://127.0.0.1:10808',HTTPS_PROXY='socks5://127.0.0.1:10808',NO_PROXY='localhost,127.0.0.1,::1',TMPDIR=str(private))
        run('01-update',[args.oo,'update'],env,private)
        run('02-install',[args.oo,'install','command-line-tools@26.0.0.201'],env,private,timeout=2400)
        package=root/'packages/command-line-tools/26.0.0.201'
        state=json.loads((root/'state/installed.json').read_text())
        artifact=state['packages']['command-line-tools']['versions']['26.0.0.201']['artifact']
        assert state['schema_version']==3 and len(artifact['binaries'])==68
        result['artifact']=artifact['url'];result['sha256']=artifact['sha256'];result['size']=artifact['size']
        result['installed_command_count']=len(artifact['binaries'])
        for name in artifact['binaries']:
            assert (root/'bin'/name).is_symlink() and (root/'bin'/(name+'@26.0.0.201')).is_symlink()
            assert (root/'bin'/name).resolve()==package/'.oo-launchers'/name
        for name in ['node','npm','npx','corepack','js_rawheap_translator']:
            assert not (root/'bin'/name).exists()
        result['private_node_not_exported']=True
        child=dict(env)
        child.update(PATH=str(root/'bin')+':'+env['PATH'],NODE_HOME='incorrect-global-node',DEVECO_SDK_HOME='incorrect-global-sdk',HVIGOR_USER_HOME=str(private/'hvigor-home'),OHPM_USER_HOME=str(private/'ohpm-home'),PYTHONDONTWRITEBYTECODE='1')
        for name in ['clang','clang++','cmake','cpack','ctest','ninja','llvm-readelf']:
            run('03-'+name.replace('+','p'),[root/'bin'/name,'--version'],child,private)
        for name in ['hvigor','hvigorw']:
            run('04-'+name,[root/'bin'/name,'--version','--no-daemon'],child,private)
        run('04-ohpm',[root/'bin/ohpm','--version'],child,private)
        run('05-version-entry',[root/'bin/hvigor@26.0.0.201','--version','--no-daemon'],child,private)
        source=private/'hello.c';source.write_text('#include <stdio.h>\nint main(void){puts("official SDK native compiler");return 0;}\n')
        for arch in ['aarch64','armv7','loongarch64','x86_64']:
            for compiler in ['clang','clang++']:
                name=f'{arch}-unknown-linux-ohos-{compiler}'
                run('06-'+name.replace('+','p'),[root/'bin'/name,'-###','-c',source],child,private)
        run('07-native-compile',[root/'bin/aarch64-unknown-linux-ohos-clang',source,'-o',private/'hello'],child,private)
        # Linked CRT objects carry an upstream .codesign section, which is not
        # a usable self signature for this executable. Modify only our probe.
        run('07-remove-inherited-signature',[root/'bin/llvm-objcopy','--remove-section=.codesign',private/'hello',private/'hello-unsigned'],child,private)
        run('07-sign-native',[root/'bin/binary-sign-tool','sign','-selfSign','1','-inFile',private/'hello-unsigned','-outFile',private/'hello-signed'],child,private)
        run('07-native-signature',[root/'bin/binary-sign-tool','display-sign','-inFile',private/'hello-signed'],child,private)
        run('07-run-native',[private/'hello-signed'],child,private)
        result['native_self_signed_execution_verified']=True
        signing=args.output/'hap-signing';signing.mkdir(exist_ok=True)
        child.update(OHECO_TOOLS_ROOT=str(package),OHECO_HVIGOR_COMMAND=str(root/'bin/hvigorw'),OHECO_PNPM_ARCHIVE=str(args.pnpm_archive.resolve(strict=True)),OHECO_VALIDATION_OUTPUT=str(signing))
        run('08-hvigor-signing',[shutil.which('python3'),Path(__file__).with_name('verify-hap.py')],child,private,timeout=600)
        result['hap_signing']=json.loads((signing/'signing-result.json').read_text())['status']
        run('09-switch',[args.oo,'switch','command-line-tools','26.0.0.201'],env,private)
        run('10-unlink',[args.oo,'unlink','command-line-tools'],env,private)
        assert package.is_dir() and not (root/'bin/hvigor').exists()
        run('11-restore',[args.oo,'switch','command-line-tools','26.0.0.201'],env,private)
        run('12-remove',[args.oo,'remove','command-line-tools@26.0.0.201','-y'],env,private)
        assert not package.exists() and not (root/'bin/hvigor').exists()
        result['status']='passed'
    result['isolated_root_cleaned']=not private.exists()
except BaseException as error:
    result.update(status='failed',error=str(error))
    print(type(error).__name__+': '+str(error),flush=True)
finally:
    if server:server.shutdown();server.server_close()
    save()
print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
raise SystemExit(0 if result['status']=='passed' else 1)
