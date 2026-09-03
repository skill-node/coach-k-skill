# Coach K — 教练对话 Agent Skill

在 Claude Code / Codex / WorkBuddy 里直接使用的专业教练对话技能。
**无需任何 API key**，使用宿主自带的模型。

三种用法：

| | 你是 | AI 是 | 用来干什么 |
|---|---|---|---|
| **被教练** | 来访者 | 教练 | 梳理职场困惑、职业方向、目标卡点、情绪 |
| **演练场** | 教练 | 来访者 | 练习教练技术，18 个预设案例，演完给 ICF 点评 |
| **复盘** | — | ICF 督导 | 拿真实的 1-on-1 记录打分，给改进建议 |

内置四套教练方法论，按话题自动选：ICF 深度倾听 / GROW / 盖洛普优势 / NLP。
不需要你选模型，说人话就行。

## 安装

```bash
npx skills add skill-node/coach-k-skill
```

一条命令装进你的 agent。技能走的是公开的 [Agent Skills](https://code.claude.com/docs/en/skills)
格式 —— 一个 `SKILL.md` 加一段 YAML，不绑定任何一家。Claude Code、Codex、Cursor、OpenCode、
WorkBuddy、千问办公等七十多个 runtime 读同一份格式，装一次，换个 agent 它还在。

不想碰命令行，把 `https://github.com/skill-node/coach-k-skill` 发给你正在用的 agent，
说一句「把这个技能装上」。它会自己读仓库，放进这台机器该放的位置 —— 各家 agent 的技能目录
都不一样，这些不用你记。

装完直接说需求，或者 `/coach-k`。卸载：`npx skills remove coach-k`。

<details>
<summary><b>你的 runtime 没有 <code>skills</code> 命令</b>，或者想从本地目录装</summary>

克隆下来跑安装脚本，它把这个目录软链到你装了的宿主对应位置（幂等，可重复运行）：

```bash
git clone https://github.com/skill-node/coach-k-skill.git
cd coach-k-skill && bash tools/install.sh
```

| 宿主 | 位置 | 调用方式 |
|---|---|---|
| Claude Code | `~/.claude/skills/coach-k` | 直接说需求，或 `/coach-k` |
| Codex CLI | `~/.agents/skills/coach-k` | 直接说需求，或 `$coach-k` |
| WorkBuddy | 在设置里导入本目录 | 技能列表中选择 |

手动装就是一句 `ln -s`：

```bash
ln -s "$(pwd)" ~/.claude/skills/coach-k
ln -s "$(pwd)" ~/.agents/skills/coach-k
```

卸载：`bash tools/install.sh --uninstall`

</details>

## 用起来

直接说人话，不用记命令：

```
我最近工作特别烦，想聊聊
```
→ 进入被教练模式。它会先帮你把话题说清楚，再切到合适的方法论。全程不给建议。

```
我想练练教练，来个难一点的职场冲突
```
→ 从案例库里挑一个匹配的，直接以角色身份开场。你来提问，它演那个有情绪、有隐情、
一开始不肯说实话的人。聊够 5 轮后说「结束」，出一份 ICF 标准的点评报告。

```
点评一下 ./coaching-sessions/2026-08-26-1430-dojo-work_cross_conflict.md
```
→ 按 ICF 核心能力（积极倾听 / 强有力提问 / 共情与同在）逐项打分，引用原话，
给出「试着这样提问」的具体改法。

会话记录自动存到 `./coaching-sessions/`（不在项目目录时存 `~/coaching-sessions/`），
存下来的文件可以直接拿去复盘。

## 案例库

18 个演练案例，三类各 6 个，难度 2–5：

- **职场**：绩效面谈、晋升后的迷茫、跨部门冲突、外行的指挥、错位的销冠、留守者的良知
- **个人**：拖延症的挣扎、冒充者综合症、讨好型人格、社交恐惧、无法忍受的「愚蠢」、三分钟热度
- **生活**：金手铐的困局、失控的父子、丧偶式育儿、退休后的真空、异地恋的信任、三明治夹心层

每个案例都有隐藏动机 —— 角色一开始会防御、会说「我觉得我没问题」，
只有当你真的接住了他的情绪，才会一点点说出真话。这是练共情的地方。

完整列表见 `scenarios/index.md`。

## 和 Web 版的关系

本 skill 是 Coach K 的本地免费版本。登录、云端跨设备历史、订阅计费在 Web 版上：

**👉 https://coach.skillnode.ai**

打开就能用，不用装任何东西，手机上也能聊。

两边共享同一份教练方法论与案例库：本包 `references/` 和 `scenarios/` 里的
markdown 就是唯一数据源，Web 版后端消费的是由 `tools/build.py` 从它们生成的产物。
改一处，两边同时生效。

## 自己改内容

- **改教练方法论** → 改 `references/models/*.md` 或 `references/discovery.md` 里
  `<!-- shared:start -->` ... `<!-- shared:end -->` 之间的部分。
- **改会话流程** → 改 `references/flow-*.md`（这部分是 skill 专属，不共享）。
- **加/改演练案例** → 改 `scenarios/cases/*.md`，`order` 决定展示顺序。

改完跑一次：

```bash
python3 tools/build.py        # 重新生成索引与产物
python3 tools/preflight.py    # 发布前自检
```

## 目录

```
SKILL.md                 入口：分诊 + 跨 flow 硬规则
references/
  flow-coachee.md        被教练全流程
  flow-dojo.md           演练场全流程
  flow-review.md         复盘点评 + ICF 评分骨架
  discovery.md           话题探索期
  routing.md             四模型选择判据
  models/*.md            GROW / 盖洛普 / NLP / ICF
scenarios/
  index.md               案例索引
  cases/*.md             18 个案例人设
tools/
  install.sh             安装 / 卸载
  build.py               由 markdown 源生成索引与后端产物
  preflight.py           发布前自检
```

## License

MIT，见 LICENSE。
