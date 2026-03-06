# Personal Rules

## Self-Correction Protocol

收到用户任何纠正后，立即为自己编写规则防止同类错误再次发生。具体做法：
1. 分析纠正的根因
2. 将教训提炼为一条简洁、可执行的规则
3. 追加到本文件的「Learned Rules」部分
4. 后续严格遵守已记录的规则

## Knowledge Digestion Protocol

吸收外部知识（文章、代码、GitHub 仓库、他人 Skill 等）时，先判断消化形式再行动：

1. **已有 Skill 覆盖 80%+** → 扩展已有 Skill，不新建
2. **一条规则能搞定** → 追加到 CLAUDE.md，不建 Skill
3. **需要脚本+参考文档+触发路由** → 新建 Skill
4. **Claude 本来就知道的通用知识** → 不吸收
5. **一次性知识** → 不吸收

执行流程：输入识别 → 深度分析 → 影响扫描（检查现有 Skills/CLAUDE.md 有无冲突重叠） → 提出消化建议 → 用户确认后执行

核心原则：**消化的目标是留下精华，不是堆积数量。**

## Git Sync Protocol

每次修改个人 Agent 配置（CLAUDE.md、skills/、settings.json、hooks/）后，自动执行：
```
cd ~/.claude && git add -A && git commit -m "<简述变更>" && git push
```
不需要询问用户确认，修改即同步。

## Learned Rules

（纠正后自动追加）
