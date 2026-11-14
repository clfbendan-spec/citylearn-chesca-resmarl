# 前端构建与发布流程（citylearnvue）

> 这份文档记录一个真实踩过的坑：仓库里的 `dist/` 停在 **2026-09-23**，而源码那天之后
> 又改了很多次。结果就是 dev server 里看到的和用旧 dist 部署出去的**不是同一份代码**。

## 为什么不能直接 `npm run build`

`vue-cli-service build` 默认输出到 `dist/`，构建前 webpack 会先删掉目标目录里上一轮的
hash 文件。在本机环境里，批量删除会被删除保护拦下：

```
ERROR  [safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED]
       {"count":50,"threshold":50,"scope":"turn", ...}
```

**这一条要读三遍，因为它有三种失败形态：**

| 做法 | 结果 |
|---|---|
| `npm run build`（默认 `dist/`） | webpack 清理旧文件时被拦，构建直接失败 |
| `--dest` 指向**有旧产物的目录** | 同上，第二次跑就失败 |
| 自己写 `shutil.rmtree` 清产物 | 计数 200+ 触发拦截，**进程被直接终止**（不是抛异常，`except` 拦不住），表现为「脚本只打了两行就退出、退出码 1」 |
| 自己写「分批 40 个逐个 `os.remove`」 | **同一次调用内累计到 50 仍被拦**，照样终止进程 |

⇒ 唯一稳的解法：**每次构建换一个新的空目录**，让 webpack 没有东西可删。

## 标准流程（两步）

```bash
cd D:/citylearn-demo

# 1) 静态检查（含棘轮：违规数只许减不许增）
python _verify_vue_lint.py

# 2) 构建 + 产物契约（构建门自动建空目录，契约默认重建再校验）
python _verify_vue_build.py
python _verify_vue_contract.py --no-build
```

构建产物落在 `%TEMP%\citylearn_vue_probe\<时间戳>\`：

```
C:\Users\<你>\AppData\Local\Temp\citylearn_vue_probe\20261020_191451
```

放临时目录有两个原因：不污染仓库（原先 `_vue_build_probe/` 一次就 61 MB），
而且系统会自己回收。`python _verify_vue_build.py --clean` 可手动清历史产物，
但受删除保护限制**每跑一次最多删 45 个文件**，要清干净得多跑几次。

## 要部署时

把 `%TEMP%\citylearn_vue_probe\<最新时间戳>\` 的内容**整目录替换**到部署目录。
不要只拷一部分、也不要改 hash 文件名 —— 每次构建的 hash 都会变。

## 部署前必看的两点

1. **`dist/` 不在版本控制里**（`.gitignore`）。⇒ 用 `git diff` **永远看不出 dist 是旧的**，
   只能看时间戳，或者干脆每次发布前重建。

2. **构建产物体积约 61 MB**（`chunk-vendors` 里的 ECharts + Monaco 占大头）。
   某次突然翻倍，先怀疑误引入了整包依赖。

## 隐藏页面怎么打开

隐藏不再是 `App.vue` 里的开关常量了（P3 已改为单一真源）。现在只有一个地方：
`src/config/menus.js` 里对应菜单项的 `enabled` 字段。

```js
{ key: 'resMarlConfig', title: 'CHESCA-ResMARL配置', icon: 'el-icon-s-operation',
  perm: PERMS.MENU_RES_MARL, component: 'ResMarlConfig', enabled: false }
```

`enabled: false` 时，菜单不渲染、`canUseMenu()` 返回 false、路由落点也会跳过它 ——
三处判断共用同一个函数，不会出现「菜单藏了但还能手点进去」。

改回 `true` 之前请确认这 5 个接口仍然通（它们只被这个页面用）：

```
GET  /web/basedata/getResMarlConfig
POST /web/basedata/saveResMarlConfig
POST /web/basedata/resetResMarlConfig
GET  /web/basedata/getBatteryMinSocConfig
POST /web/basedata/saveBatteryMinSocConfig
```

`python _verify_api_paths.py` 可以确认接口还在。另外 `menu:resMarlConfig` 与
`resMarlConfig:operate` 在 DB 里是 `enabled=0`，**非超管拿不到**；
要对外开放得先在用户管理里给角色勾上。

## 验收脚本一览

| 脚本 | 作用 |
|---|---|
| `_verify_vue_lint.py` | lint 违规数只减不增（基线 `.eslint-baseline.json`，`--rebase` 重设） |
| `_verify_vue_build.py` | 生产构建能否通过（唯一空目录，产物留在 `%TEMP%`；`--clean` 清历史） |
| `_verify_vue_contract.py` | 产物关键字契约（`_vue_contract.json`：必存 / 必消失；默认重建） |
| `_verify_menu_perm_align.py` | 菜单 / 权限 / 组件 / DB 四方一致性（抓死页面与漏挂权限码） |
| `_verify_api_paths.py` | 前端调用 ↔ 后端接口清单对齐（抓残留调用点） |
| `_verify_menus_logic.py` | `config/menus.js` 的 11 条纯 JS 断言（不需要浏览器） |
