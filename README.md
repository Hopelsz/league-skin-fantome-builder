# 英雄联盟皮肤fantome构建器

## 介绍

构建每个皮肤的.fantome从本地英雄联盟安装中生成的mod文件。

提取所有的英雄列表的每个皮肤、炫彩和形态，并使用单个命令将它们提取到可直接使用的fantome包中。

> **不想自己构建？** 去[LeagueSkins](https://github.com/bettie9/LeagueSkins)获取预提取的皮肤包。

> **不要为免费的东西付费。** 不要使用付费的皮肤更改器 — 皮肤mod是免费的，信息应该免费。

***



## 环境要求

- Python 3.11+
- pip 23.0+


## 安装依赖

```powershell
pip install -r requirements.txt
```
## 使用
下载所有英雄的皮肤、炫彩和形态，需要约 3-5分钟。
```powershell
python build.py `--league "M:\网络游戏\英雄联盟" `--out .\out
```

首次运行时将CommunityDragon哈希表（~50 MB）下载到 pref/hashes/cdtb_hashes/并缓存它们。在--refresh-hashes添加联盟补丁后重新拉取。

完整阵容（170+英雄，所有皮肤+炫彩+形态）需要约3-5分钟。

### 标志

| 命令               | 描述                                     |
| ------------------ | ----------------------------------------------- |
| `--league <path>`  | 英雄联盟安装根目录，选择*英雄联盟*文件夹，无需指定子目录（必填）                    |
| `--out <dir>`      | 输出目录（必填）                                |
| `--only Ahri,Nami` | 仅构建这些英雄的皮肤、炫彩和形态（逗号分隔）[可选]  |
| `--limit N`        | 每个英雄最多构建N个皮肤（用于快速测试）[可选]  |
| `--refresh-hashes` | 强制重新下载CommunityDragon哈希表 [可选] |
| `--chromas` | 包含炫彩，跳过询问 [可选] |
| `--no-chromas` | 不包含炫彩，跳过询问 [可选] |

### 快速测试

```powershell
python build.py --league "M:\网络游戏\英雄联盟" --out .\out --only Ekko --limit 8
```
### 工作原理

去看[这里](https://github.com/bettie9/LeagueSkins)。