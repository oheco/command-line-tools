#!/usr/bin/env python3
"""Verify official Hvigor HAP signing with disposable encrypted credentials.

No adapter preload, dependency download, daemon, user signing material, or Godot
changes. All credentials and projects are private under TMPDIR and cleaned up.
Only redacted logs, result metadata, and a synthetic signed HAP are retained.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile

BASE = Path(os.environ['OHECO_TOOLS_ROOT']).resolve(strict=True)
OUTPUT = Path(os.environ['OHECO_VALIDATION_OUTPUT']).resolve(strict=True)
SDK = BASE / 'sdk/default/openharmony'
BUNDLE = 'org.oheco.commandlinetools'
RESULT = {'status': 'running', 'distribution_version': '26.0.0.201', 'hvigor': '7.26.8',
          'sdk': '26.0.0.105', 'steps': [], 'adapter_loaded': False,
          'device_installation_verified': False, 'credentials_cleaned': False}
REDACTIONS = []


def save_result():
    with (OUTPUT / 'signing-result.json').open('w') as stream:
        stream.write(json.dumps(RESULT, ensure_ascii=False, indent=2) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def digest(file):
    with file.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def redact(text):
    for secret in sorted(set(REDACTIONS), key=len, reverse=True):
        text = text.replace(secret, '<redacted>')
    return text


def run(label, command, cwd, env, timeout=60, expect_failure=False):
    RESULT['active_step'] = label
    RESULT['step_started_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    save_result()
    print(label, flush=True)
    process = subprocess.Popen(list(map(str, command)), cwd=cwd, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, start_new_session=True)
    timed_out = False
    try:
        log, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGTERM)
        try:
            log, _ = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            log, _ = process.communicate()
    cleaned = redact(log)
    (OUTPUT / (label + '.log')).write_text(cleaned)
    print('exit:', process.returncode, flush=True)
    print(cleaned[-10000:], flush=True)
    RESULT['steps'].append({'label': label, 'exit_code': process.returncode,
                            'expected_failure': expect_failure, 'timeout': timed_out})
    save_result()
    if timed_out or (process.returncode == 0) == expect_failure:
        raise RuntimeError(label + (' timed out' if timed_out else ' returned an unexpected exit code'))
    return cleaned


def fixture_module():
    path = Path(__file__).resolve().with_name('hap-fixture.py')
    spec = importlib.util.spec_from_file_location('fixture_only', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    tempbase = Path(os.environ['TMPDIR']).resolve()
    temporary = tempfile.TemporaryDirectory(prefix='official-hvigor-signed-hap-', dir=tempbase)
    private = Path(temporary.name).resolve()
    assert private.parent == tempbase and private.name.startswith('official-hvigor-signed-hap-')
    source_files = [BASE / 'hvigor/hvigor/bin/hvigor.js',
                    BASE / 'hvigor/hvigor/src/common/util/path-util.js',
                    BASE / 'hvigor/hvigor-ohos-plugin/src/tasks/sign-hap.js',
                    BASE / 'hvigor/hvigor-ohos-plugin/src/utils/decipher-util.js',
                    BASE / 'hvigor/hvigor-ohos-plugin/src/tasks/sign/command-builder-impl/hap-sign-command-builder.js']
    before = {str(file.relative_to(BASE)): digest(file) for file in source_files}
    try:
        fixture = fixture_module()
        project = private / 'project with spaces'
        project.mkdir()
        profile = fixture.project_fixture(project)
        product = profile['app']['products'][0]
        product.update(runtimeOS='HarmonyOS', targetSdkVersion='26.0.0', compatibleSdkVersion='26.0.0')
        product.pop('compileSdkVersion')
        modules = project / 'node_modules/@ohos'
        modules.mkdir(parents=True)
        for package in ['hvigor', 'hvigor-ohos-plugin']:
            (modules / package).symlink_to(BASE / 'hvigor' / package, target_is_directory=True)
        env = dict(os.environ)
        for key in ['NODE_OPTIONS', 'JAVA_HOME', 'OHOS_SDK_HOME', 'OHOS_BASE_SDK_HOME', 'HOS_SDK_HOME']:
            env.pop(key, None)
        paths = [Path(os.environ['OHECO_HVIGOR_COMMAND']).parent, SDK / 'native/llvm/bin', SDK / 'native/build-tools/cmake/bin',
                 SDK / 'toolchains', SDK / 'toolchains/lib', Path('/usr/bin'), Path('/bin')]
        env.update(PATH=os.pathsep.join(map(str, paths)), NODE_HOME='invalid-parent-node',
                   NODE_PATH=str(project / 'node_modules'), DEVECO_SDK_HOME='invalid-parent-sdk',
                   HVIGOR_USER_HOME=str(private / 'hvigor-home'), TMPDIR=str(private),
                   npm_config_cache=str(private / 'npm-cache'),
                   npm_config_userconfig=str(private / 'npmrc'),
                   npm_config_globalconfig=str(private / 'global-npmrc'),
                   npm_config_prefix=str(private / 'npm-prefix'),
                   npm_config_offline='true', npm_config_audit='false', npm_config_fund='false')
        for name in ['npmrc', 'global-npmrc']:
            (private / name).write_text('')
        node = BASE / 'node/bin/node'
        pnpm_archive = Path(os.environ['OHECO_PNPM_ARCHIVE']).resolve(strict=True)
        assert pnpm_archive.stat().st_size == 4197451
        assert digest(pnpm_archive) == 'afa99b0b4b3d11c1dad2b472f9318ae2c78673829749ded527f89f09071479a7'
        wrapper_tools = private / 'hvigor-home/wrapper/tools/10.28.2'
        wrapper_tools.mkdir(parents=True)
        run('00-prepare-wrapper-pnpm', [node, BASE / 'node/lib/node_modules/npm/bin/npm-cli.js',
            'install', '--offline', '--ignore-scripts', '--no-audit', '--no-fund',
            '--package-lock=false', '--prefix', wrapper_tools, pnpm_archive], project, env)
        run('00-wrapper-pnpm-version', [node, wrapper_tools / 'node_modules/pnpm/bin/pnpm.cjs',
            '--version'], project, env)
        RESULT['wrapper_pnpm'] = {'version': '10.28.2',
            'sha256': 'afa99b0b4b3d11c1dad2b472f9318ae2c78673829749ded527f89f09071479a7',
            'prepared_from_verified_registry_archive': True, 'offline_build': True}
        signer = SDK / 'toolchains/lib/hap-sign-tool'
        password = 'Disposable pass ' + secrets.token_hex(16)
        wrong_password = 'Incorrect pass ' + secrets.token_hex(16)
        REDACTIONS.extend([password, wrong_password])
        store = private / 'credentials.p12'
        common = {'keystoreFile': store, 'keystorePwd': password, 'keyPwd': password}

        def sign(label, action, **options):
            command = [signer, action]
            for name, value in options.items():
                command.extend(['-' + name, str(value)])
            return run(label, command, project, env)

        root_dn = 'CN=Official Hvigor Disposable Root,O=oheco,C=CN'
        sub_dn = 'CN=Official Hvigor Disposable Intermediate,O=oheco,C=CN'
        ca = {'keyAlg': 'ECC', 'keySize': 'NIST-P-256', 'validity': 2,
              'signAlg': 'SHA256withECDSA', **common}
        sign('01-root-ca', 'generate-ca', keyAlias='root', subject=root_dn,
             outFile=private / 'root.cer', **ca)
        sign('02-intermediate-ca', 'generate-ca', keyAlias='intermediate', subject=sub_dn,
             issuer=root_dn, issuerKeyAlias='root', issuerKeyPwd=password,
             basicConstraintsPathLen=0, outFile=private / 'sub.cer', **ca)
        for index, (alias, action) in enumerate([('app', 'generate-app-cert'), ('profile', 'generate-profile-cert')]):
            sign(f'03-{index}-{alias}-key', 'generate-keypair', keyAlias=alias,
                 keyAlg='ECC', keySize='NIST-P-256', **common)
            sign(f'04-{index}-{alias}-cert', action, keyAlias=alias,
                 subject=f'CN=Official Hvigor Disposable {alias},O=oheco,C=CN', issuer=sub_dn,
                 issuerKeyAlias='intermediate', issuerKeyPwd=password, validity=2,
                 signAlg='SHA256withECDSA', outForm='certChain',
                 rootCaCertFile=private / 'root.cer', subCaCertFile=private / 'sub.cer',
                 outFile=private / (alias + '-chain.cer'), **common)
        unsigned = json.loads((signer.parent / 'UnsgnedDebugProfileTemplate.json').read_text())
        unsigned['uuid'] = str(uuid.uuid4())
        now = int(time.time())
        unsigned['validity'] = {'not-before': now - 60, 'not-after': now + 86400}
        leaf = (private / 'app-chain.cer').read_text().split('-----END CERTIFICATE-----')[0] + '-----END CERTIFICATE-----\n'
        unsigned['bundle-info'].update({'bundle-name': BUNDLE, 'developer-id': 'official-hvigor-disposable-test',
                                        'development-certificate': leaf})
        unsigned['acls']['allowed-acls'] = []
        unsigned['permissions']['restricted-permissions'] = []
        unsigned['debug-info']['device-ids'] = ['0' * 64]
        fixture.write_json(private / 'profile.json', unsigned)
        sign('05-sign-profile', 'sign-profile', mode='localSign', keyAlias='profile',
             signAlg='SHA256withECDSA', profileCertFile=private / 'profile-chain.cer',
             inFile=private / 'profile.json', outFile=private / 'profile.p7b', **common)
        sign('06-verify-profile', 'verify-profile', inFile=private / 'profile.p7b',
             outFile=private / 'verified-profile.json')
        verified = json.loads((private / 'verified-profile.json').read_text())
        assert verified['bundle-info']['bundle-name'] == BUNDLE

        secret_input = private / 'password-input.json'
        fixture.write_json(secret_input, {'password': password, 'wrongPassword': wrong_password})
        crypto_script = r"""
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {DecipherUtil:C}=require(process.argv[1]);
const root=process.argv[2],secrets=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
const directory=path.join(root,'material');fs.mkdirSync(directory);
function file(dir,name,data){fs.mkdirSync(dir,{recursive:true});fs.writeFileSync(path.join(dir,name),data);}
const components=[crypto.randomBytes(16),crypto.randomBytes(16),crypto.randomBytes(16)];
components.forEach((value,index)=>file(path.join(directory,'fd',String(index)), 'value', value));
const salt=crypto.randomBytes(16);file(path.join(directory,'ac'),'value',salt);
const rootKey=C.getRootKey(components.map(v=>new Int8Array(v)),new Int8Array(salt),'disposable fixture');
const workKey=crypto.randomBytes(16);
function encrypt(key,data){const iv=crypto.randomBytes(12),cipher=crypto.createCipheriv('aes-128-gcm',key,iv);
 const encoded=Buffer.concat([cipher.update(data),cipher.final(),cipher.getAuthTag()]);
 const length=Buffer.alloc(4);length.writeUInt32BE(encoded.length);return Buffer.concat([length,iv,encoded]);}
file(path.join(directory,'ce'),'value',encrypt(rootKey,workKey));
const good=encrypt(workKey,Buffer.from(secrets.password)).toString('hex');
const bad=encrypt(workKey,Buffer.from(secrets.wrongPassword)).toString('hex');
if(C.decryptPwd(root,good,'disposable fixture')!==secrets.password||C.decryptPwd(root,bad,'disposable fixture')!==secrets.wrongPassword)throw Error('Official password format validation failed');
fs.writeFileSync(path.join(root,'encrypted-passwords.json'),JSON.stringify({good,bad}));
console.log('Official encrypted password/material round trip passed');
"""
        run('07-official-password-format', [node, '-e', crypto_script,
             BASE / 'hvigor/hvigor-ohos-plugin/src/utils/decipher-util.js', private, secret_input], project, env)
        encrypted = json.loads((private / 'encrypted-passwords.json').read_text())
        REDACTIONS.extend(encrypted.values())
        material = {'storeFile': str(store), 'storePassword': encrypted['good'], 'keyAlias': 'app',
                    'keyPassword': encrypted['good'], 'signAlg': 'SHA256withECDSA',
                    'profile': str(private / 'profile.p7b'), 'certpath': str(private / 'app-chain.cer')}
        profile['app']['signingConfigs'] = [{'name': 'disposable', 'type': 'HarmonyOS', 'material': material}]
        product['signingConfig'] = 'disposable'
        fixture.write_json(project / 'build-profile.json5', profile)
        command = [Path(os.environ['OHECO_HVIGOR_COMMAND']), '--mode', 'module', '-p',
                   'module=entry@default', '-p', 'product=default', '-p', 'buildMode=debug',
                   'assembleHap', '--no-daemon', '--no-incremental', '--stacktrace']
        run('08-official-hvigor-signed-hap', command, project, env, timeout=180)
        artifacts = list((project / 'entry/build/default/outputs/default').glob('*-signed.hap'))
        assert len(artifacts) == 1 and artifacts[0].stat().st_size > 0, 'No fresh signed HAP'
        hap = artifacts[0]
        sign('09-verify-signed-hap', 'verify-app', inFile=hap,
             outCertChain=private / 'verified-app-chain.cer', outProfile=private / 'verified-app-profile.p7b')
        assert (private / 'verified-app-profile.p7b').read_bytes() == (private / 'profile.p7b').read_bytes()
        with zipfile.ZipFile(hap) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                assert Path(info.filename).suffix.lower() not in ('.p12', '.pfx', '.jks', '.key')
                content = archive.read(info)
                assert b'PRIVATE KEY-----' not in content
                assert all(value.encode() not in content for value in REDACTIONS)
        public_hap = OUTPUT / 'entry-default-signed.hap'
        shutil.copyfile(hap, public_hap)
        RESULT['signed_hap'] = {'file': public_hap.name, 'size': public_hap.stat().st_size,
                                'sha256': digest(public_hap), 'native_verified': True,
                                'profile_matches': True, 'bundle_name': BUNDLE}
        save_result()

        tampered = private / 'tampered.hap'
        data = bytearray(hap.read_bytes())
        with zipfile.ZipFile(hap) as archive:
            entry = next(info for info in archive.infolist() if info.filename.endswith('.abc') and info.compress_size > 10)
        offset = entry.header_offset
        filename_len, extra_len = struct.unpack_from('<HH', data, offset + 26)
        data[offset + 30 + filename_len + extra_len + 5] ^= 1
        tampered.write_bytes(data)
        tamper_log = run('10-reject-tampered-hap', [signer, 'verify-app', '-inFile', tampered,
                         '-outCertChain', private / 'tampered-chain.cer',
                         '-outProfile', private / 'tampered-profile.p7b'],
                         project, env, expect_failure=True)
        assert (('digest' in tamper_log.lower() and any(word in tamper_log.lower() for word in ['fail', 'error', 'mismatch']))
                or 'verify merkle tree bytes failed' in tamper_log.lower())
        assert 'is required' not in tamper_log.lower()
        RESULT['tampered_hap_rejected'] = True
        # Keep a successful signed artifact as evidence, then remove only the
        # precisely identified output in the disposable project for the control.
        assert hap.resolve().is_relative_to(project.resolve()) and hap.name.endswith('-signed.hap')
        hap.unlink()
        wrong_profile = copy.deepcopy(profile)
        wrong_profile['app']['signingConfigs'][0]['material']['storePassword'] = encrypted['bad']
        fixture.write_json(project / 'build-profile.json5', wrong_profile)
        wrong_log = run('11-reject-incorrect-keystore-password', command, project, env,
                        timeout=180, expect_failure=True)
        assert any(word in wrong_log.lower() for word in ['keystore', 'password', 'decrypt'])
        assert not list((project / 'entry/build/default/outputs/default').glob('*-signed.hap'))
        RESULT['incorrect_password_rejected'] = True
        RESULT['status'] = 'passed'
    except BaseException as error:
        RESULT['status'] = 'failed'
        RESULT['error'] = redact(str(error))
        print(type(error).__name__ + ': ' + redact(str(error)), flush=True)
    finally:
        after = {str(file.relative_to(BASE)): digest(file) for file in source_files}
        RESULT['official_js_fingerprints'] = before
        RESULT['checked_official_js_unchanged'] = before == after
        assert private.parent == tempbase and private.name.startswith('official-hvigor-signed-hap-')
        temporary.cleanup()
        RESULT['credentials_cleaned'] = not private.exists()
        save_result()
    print(json.dumps(RESULT, ensure_ascii=False, indent=2), flush=True)
    return 0 if RESULT['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
