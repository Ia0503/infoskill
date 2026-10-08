# infoskill

根据已有项目的源码、配置、测试和开发日志，生成或更新中文 `info/` 资料及适用的一键操作脚本。适合项目复盘、源码学习和面试准备。

## 安装

下载本仓库，将包含 `SKILL.md` 的文件夹放到所用工具的 skill 目录，并命名为 `infoskill`。不要多嵌套一层下载目录。

| 工具 | 仅当前项目 | 个人所有项目 |
| --- | --- | --- |
| Codex | `<项目>/.agents/skills/infoskill/` | `~/.agents/skills/infoskill/` |
| Claude Code | `<项目>/.claude/skills/infoskill/` | `~/.claude/skills/infoskill/` |

`~` 表示用户主目录。首次未发现时重新打开会话或重启工具。目录规则和调用方式以各平台版本为准：[Codex](https://learn.chatgpt.com/docs/build-skills)、[Claude Code](https://code.claude.com/docs/en/skills)。

也可通过本仓库的打包工具导出仅含 skill 运行资源的 ZIP，解压到上述位置。直接安装源码仓库时，`test/` 无需加载到模型上下文。

## 使用

在目标项目中发起请求：

```text
使用 $infoskill，为当前项目生成 info 文档和一键操作脚本。
```

```text
使用 $infoskill，只更新第 04 和第 05 份文档，保留其他资料。
```

Claude Code 可使用 `/infoskill`。支持隐式选择的平台也可依据描述自动选择。Skill 由 AI 读取执行，不是后台监听程序。

## 输出

文档位于目标项目 `info/`：

1. 项目总览与架构
2. 目录结构与文件详解
3. 技术选型与对比分析
4. 核心模块深度剖析
5. 测试评测与部署维护
6. 面试高频问题与回答要点
7. 开发日志与阶段总结——仅在原有 `info/log/` 有有效记录时生成

适用时生成控制脚本，并在同目录写 `脚本使用说明.txt`。Windows 优先 BAT，复杂流程可调用 PowerShell；其他格式取决于项目与环境。没有长期服务的项目不强制生成启停脚本。

整个 `info/` 应被 Git 忽略；已跟踪的文件仅报告，不自动移除跟踪。原始日志和无关个人资料保留。生成脚本不会自动启停服务、安装依赖或执行付费调用。

## 运行条件与验证边界

AI 工具需要能读取目标项目并写入输出。普通文档整理可直接按规则执行；附带扫描、校验和打包工具使用 Python 3.10+ 标准库。Windows 脚本的具体要求以生成的 TXT 为准。

核心格式遵循 Agent Skills，平台专属发现目录和调用方式需分别安装。当前验证聚焦 Python 辅助工具和 Windows BAT/PowerShell；其他宿主平台尚未实测。辅助检查不证明文档事实正确，仍需对照源码复核。

## 开发与导出

在仓库根目录执行；Windows 可将 `python` 换成 `py -3.12`：

```text
python -m unittest discover -s test -p "test_*.py" -v
python scripts/inspect_project.py <目标项目目录>
python scripts/validate_info.py <目标项目目录>
python scripts/validate_info.py <目标项目目录> --only 04 --only 05
python scripts/package_skill.py --output dist/infoskill.zip
```

打包工具拒绝覆盖已有 ZIP。开发记录在本地 `info/log/`，测试集中在 `test/`，验证产物在 `test/results/`；这些私有记录和产物不进入分享包。
