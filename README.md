# HarmonyOS 官方命令行工具

本仓库记录华为官方 `command-line-tools@26.0.0.201` 在 HarmonyOS PC ARM64 的发布、
oo 命令映射及验收。分发保持原始官方压缩包字节，oheco 生成的命令启动器不修改随包文件。

- 官方来源：[华为开发者下载中心](https://developer.huawei.com/consumer/cn/download/)
- [固定公共下载地址](https://s3.oheco.org/command-line-tools/26.0.0.201/commandline-tools-harmonyos-26.0.0.201.tar.gz)
- 原始归档：`tar.gz`，2183292474 字节；安装去掉一层 `command-line-tools/` 根目录。
- SHA-256：`60929c00ae486cc038ea48145497ad34dbd4ac6a25c3f2fa895ce74afb4607f5`
- SDK 26.0.0.105 / API 26，Hvigor 与插件 7.26.8，OHPM 6.0.1。

## 安装和命令

需要 oo >=0.11.0、v6 索引：

```sh
oo update
oo install oheco
oo update
oo install command-line-tools
hvigor --version --no-daemon
ohpm --version
clang --version
binary-sign-tool -h
```

显式设置旧官方 `OHECO_INDEX_URL` 的用户，升级 oo 后改用
`https://oheco.org/index/v6/index.json`。包内约 6.98 GiB 常规文件；安装同时需要压缩包
缓存及解压暂存空间。原始归档包含的 8 对大小写冲突头文件按 oo 通用规则保留全小写版本，
不重打归档；依赖大写变体定义的代码需另行适配。

提供 65 个旧 SDK 命令，以及 `hvigor`、`hvigorw`、`ohpm`，包括带 `@26.0.0.201` 的版本入口。
`js_rawheap_translator` 已退出。LLVM/CMake/签名工具保持真实相邻资源布局。目标 Clang
别名调用同一个官方 clang/clang++，安全传递原包装脚本的 target、sysroot 和 MUSL 参数，
支持含空格安装根且不修改原脚本。

Hvigor/OHPM 仅在自身子进程设置包内 `NODE_HOME`、PATH 和 `DEVECO_SDK_HOME`；
Node/npm/npx/corepack 不创建全局入口。全局命令继续由 `nodejs` 包提供。
SDK 保持 `sdk/default/{openharmony,hms}` 结构，不再生成 oo SDK 视图。
原生启动器支持空格及特殊字符，但官方 ArkTS 内部 shell 调用不能正确处理 SDK 根中的
`$` 等 shell 元字符；Hvigor 构建使用不含这些字符的安装根，不将启动器测试扩大为上游支持承诺。
本次不新增 LLDB 和 CodeLinter 命令，原始资源保留；Godot Editor 迁移另行处理。

## 本机 C/C++ 可执行文件

SDK CRT 对象会把上游 `.codesign` 段带入链接结果，该段不能直接作为新可执行文件的本机
自签名使用。对自己新建的产物移除该段，再用包内工具自签名：

```sh
aarch64-unknown-linux-ohos-clang hello.c -o hello
llvm-objcopy --remove-section=.codesign hello hello-unsigned
binary-sign-tool sign -selfSign 1 -inFile hello-unsigned -outFile hello-signed
./hello-signed
```

这只修改自己的产物，不改SDK文件。Go工具链已在最终构建后执行对应签名流程。
HAP使用工程签名配置与官方Hvigor流程；设备信任需要真实发行证书和设备验证。

## 旧安装

旧五个 `ohos-sdk-*` 和 npm `@oheco/hvigor` 从当前软件目录退出，已有文件不会随索引更新删除。
先 `oo list` 核对，仅对已有旧命令包执行：

```sh
oo unlink ohos-sdk-native ohos-sdk-toolchains
```

这只释放默认和版本命令链接，保留所有文件和原始收据。ETS/JS/previewer 原无命令，
无需 unlink。恢复需先释放新包入口，再 `oo switch <旧包> <已装版本>`。
旧 npm Hvigor 按原安装作用域卸载；若由 oo 默认全局安装，可用
`oo remove npm:@oheco/hvigor -y`。自定义 prefix/项目安装需明确选择对应作用域。

oo 0.11.0 删除 `oo sdk` 及视图卸载保护。旧视图仍指向精确组件版本，继续使用旧工程时
保留这些源版本；显式 remove/cascade/autoremove 可能令旧视图失效。
更多步骤见 [oo 迁移说明](https://github.com/oheco/oheco/blob/main/docs/MIGRATION.md)。

## 许可与来源

本仓库的发布元数据不改变华为组件许可。完整归档采用多种组件许可，第三方 NOTICE/LICENSE
随原始包完整保留，分别依照各权利人的条款。官方 Hvigor 的 package.json 标注
`SEE LICENSE IN LICENSE.txt`；归档含 NOTICE，但相应顶层 LICENSE.txt 未随包提供，因此
不能把整个官方发行包重新标为 MIT 或 Apache。本镜像不是华为官方下载域名。

## 验证

R2 上传已核对大小与 MD5，并完整读取远端内容验证 SHA-256。公共域名匿名 HEAD 返回200、
Range GET 返回206，开头1MiB和末尾16KiB与原始归档一致，不需要预签名下载。
发布前的安装、命令、资源、编译签名与官方 Hvigor HAP 验收记录保存在 `validation/`。
2026-10-11 的安装后验收实际调用 `hvigorw` 官方包装器，完成签名 HAP、独立验签、
篡改和错误密码拒绝，以及 switch/unlink/恢复/卸载；原始 JS 指纹未改变，凭据已清理。
包装器默认需要 pnpm 10.28.2，首次使用会通过随包 npm 安装它；离线环境应预先准备。
验收使用真实 npm 注册中心的固定归档，预置到隔离的 Hvigor 用户目录并隔离 npm 缓存，
未切换 `hvigor.dependency.useNpm`，也未绕过包装器直接执行主程序。

pnpm 验收输入地址为 `https://registry.npmjs.org/pnpm/-/pnpm-10.28.2.tgz`，4197451 字节，
SHA-256 为 `afa99b0b4b3d11c1dad2b472f9318ae2c78673829749ded527f89f09071479a7`；
注册中心 SHA-512 完整性记录见 `validation/pnpm-10.28.2.json`。用以下脚本复核正式安装：

```sh
python3 scripts/validate-install.py --oo /path/to/oo --output "$XDG_CACHE_HOME/tools-validation" \
  --pnpm-archive /path/to/pnpm-10.28.2.tgz
```

日常使用可把 `HVIGOR_USER_HOME` 和 npm 缓存设置到应用私有缓存目录；签名凭据放应用私有
配置或临时目录。验收记录不包含真实凭据。本轮没有观察到新重启，但此前系统
`HM_PANIC` 的具体根因尚未确认。本机验证不代表所有设备都不会发生该问题。
文件签名验证不代表真实设备安装或证书信任、APP/HSP/增量/daemon 工作流已认证。
