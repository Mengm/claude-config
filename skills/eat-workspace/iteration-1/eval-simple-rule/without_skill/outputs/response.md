好的，已记住。我会把这条规则追加到你的个人 `~/.claude/CLAUDE.md` 的 Learned Rules 部分：

**新增规则：**
- **Git commit message format**: Always use [Conventional Commits](https://www.conventionalcommits.org/) format for all git commit messages. Format: `<type>(<optional scope>): <description>`, e.g., `feat(render): add volumetric cloud pass`, `fix(gpu-driven): resolve null pointer in batch culling`, `chore: update dependencies`.

追加完成后会自动同步到你的 claude-config 仓库。

---

**实际操作：** 在 `~/.claude/CLAUDE.md` 的 `## Learned Rules` 部分末尾追加：

```
- **Git commit message format**: Always use Conventional Commits format. Structure: `<type>(<optional scope>): <description>`. Common types: `feat`, `fix`, `refactor`, `chore`, `docs`, `style`, `perf`, `test`, `ci`, `build`. Example: `feat(render): add volumetric cloud pass`.
```

然后执行 git sync：
```bash
cd ~/.claude && git add -A && git commit -m "chore: add conventional commits rule" && git push
```

从现在起，所有我帮你写的 commit message 都会遵循 Conventional Commits 格式。
