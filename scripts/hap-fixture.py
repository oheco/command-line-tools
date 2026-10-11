"""Synthetic disposable HAP project; derived from oheco/hvigor MIT fixture."""
import json
import struct
import zlib
SDK_API="26.0.0"
BUNDLE="org.oheco.commandlinetools"

def write_json(file, value):
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(value, indent=2) + '\n')

def project_fixture(root):
    texts = {
        'hvigorfile.ts': "import { appTasks } from '@ohos/hvigor-ohos-plugin';\nexport default { system: appTasks, plugins: [] };\n",
        'entry/hvigorfile.ts': "import { hapTasks } from '@ohos/hvigor-ohos-plugin';\nexport default { system: hapTasks, plugins: [] };\n",
        'entry/src/main/ets/entryability/EntryAbility.ets': "import UIAbility from '@ohos.app.ability.UIAbility';\nimport window from '@ohos.window';\nexport default class EntryAbility extends UIAbility {\n  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index'); }\n}\n",
        'entry/src/main/ets/pages/Index.ets': "import native from 'libentry.so';\n@Entry\n@Component\nstruct Index {\n  build() { Column() { Text(native.value()).fontSize(24) }.width('100%').height('100%') }\n}\n",
        'entry/src/main/cpp/types/libentry/Index.d.ts': 'export const value: () => string;\n',
        'entry/src/main/cpp/CMakeLists.txt': 'cmake_minimum_required(VERSION 3.5)\nproject(hvigor_native_probe)\nadd_library(entry SHARED probe.cpp)\ntarget_link_libraries(entry PUBLIC libace_napi.z.so)\n',
        'entry/src/main/cpp/probe.cpp': '#include <napi/native_api.h>\nstatic napi_value Value(napi_env env,napi_callback_info) { napi_value v; napi_create_string_utf8(env,"native Hvigor probe",NAPI_AUTO_LENGTH,&v);return v; }\nstatic napi_value Init(napi_env env,napi_value exports) { napi_property_descriptor p={"value",nullptr,Value,nullptr,nullptr,nullptr,napi_default,nullptr};napi_define_properties(env,exports,1,&p);return exports; }\nstatic napi_module m={1,0,nullptr,Init,"entry",nullptr,{0}};\nextern "C" __attribute__((constructor)) void Register(){napi_module_register(&m);}\n',
    }
    for relative, text in texts.items():
        file = root / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)
    docs = {
        'oh-package.json5': {'modelVersion': '6.0.0', 'name': 'hvigor-native-probe', 'version': '1.0.0', 'dependencies': {}, 'devDependencies': {}},
        'hvigor/hvigor-config.json5': {'modelVersion': '6.0.0', 'dependencies': {}, 'execution': {'daemon': False, 'parallel': False, 'incremental': False}},
        'AppScope/app.json5': {'app': {'bundleName': BUNDLE, 'vendor': 'oheco', 'versionCode': 1, 'versionName': '1.0.0', 'icon': '$media:icon', 'label': '$string:app_name'}},
        'AppScope/resources/base/element/string.json': {'string': [{'name': 'app_name', 'value': 'Hvigor Native Probe'}]},
        'entry/oh-package.json5': {'name': 'entry', 'version': '1.0.0', 'dependencies': {'libentry.so': 'file:./src/main/cpp/types/libentry'}},
        'entry/src/main/cpp/types/libentry/oh-package.json5': {'name': 'libentry.so', 'version': '1.0.0', 'types': './Index.d.ts'},
        'entry/build-profile.json5': {'apiType': 'stageMode', 'buildOption': {'externalNativeOptions': {'path': './src/main/cpp/CMakeLists.txt', 'arguments': '', 'cppFlags': '', 'abiFilters': ['arm64-v8a']}}, 'targets': [{'name': 'default'}]},
        'entry/src/main/module.json5': {'module': {'name': 'entry', 'type': 'entry', 'description': '$string:app_name', 'mainElement': 'EntryAbility', 'deviceTypes': ['2in1'], 'deliveryWithInstall': True, 'installationFree': False, 'pages': '$profile:main_pages', 'abilities': [{'name': 'EntryAbility', 'srcEntry': './ets/entryability/EntryAbility.ets', 'description': '$string:app_name', 'icon': '$media:icon', 'label': '$string:app_name', 'startWindowIcon': '$media:icon', 'startWindowBackground': '$color:start_window_background', 'exported': True, 'skills': [{'entities': ['entity.system.home'], 'actions': ['ohos.want.action.home']}]}]}},
        'entry/src/main/resources/base/element/color.json': {'color': [{'name': 'start_window_background', 'value': '#FFFFFF'}]},
        'entry/src/main/resources/base/profile/main_pages.json': {'src': ['pages/Index']},
    }
    for relative, value in docs.items():
        write_json(root / relative, value)

    def png_chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    pixels = (b'\x00' + bytes((38, 77, 213, 255)) * 64) * 64
    icon = b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', struct.pack('>IIBBBBB', 64, 64, 8, 6, 0, 0, 0)) + png_chunk(b'IDAT', zlib.compress(pixels)) + png_chunk(b'IEND', b'')
    file = root / 'AppScope/resources/base/media/icon.png'
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(icon)
    return {'app': {'products': [{'name': 'default', 'compileSdkVersion': SDK_API, 'targetSdkVersion': SDK_API, 'compatibleSdkVersion': 23, 'runtimeOS': 'OpenHarmony'}], 'buildModeSet': [{'name': 'debug'}, {'name': 'release'}]}, 'modules': [{'name': 'entry', 'srcPath': './entry', 'targets': [{'name': 'default', 'applyToProducts': ['default']}]}]}
