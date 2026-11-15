## Example Texts for Telegram Messages


### When Starting Build

Building Kernel (*Hash for this build*)
**Device**: **`device`**
**Linux Version**: **`version`**
**KernelSU**: **`kernelsu install script owner eg. backslashxx, shockwave, emredemr, kernelsu`**
**NoMount**: **`included/not included`**
**Compiler**: **`Compiler --version`**
**Action Host**: **`Hostname in Config.json`**
**Cores**: **`How many cores in used`**

### When Build Failed

Build Failed (*Hash of this build*)
```
<extracted compiler/linker errors with context>
```

The full build log is attached as a file (`kbuild_<hash>.log`) as well.

### When Build Success

Build Success (*Hash of this build*)
<anykernel3.zip>

**Device**: **`device`**
**Linux Version**: **`version`**
**KernelSU**: **`kernelsu install script owner eg. backslashxx, shockwave, emredemr, kernelsu`**
**NoMount**: **`included/not included`**
**Build Time**: **`build time`**
**SHA256**: **`sha for uploaded anykernel zip`**
```
<a small hint for latest commit on git>
```

Note: Hash is gonna be random

When GoFile is enabled, the GoFile download link is appended to the Build
Success message (both when the artifact is uploaded to Telegram and when it is
too large and only the link can be sent).
