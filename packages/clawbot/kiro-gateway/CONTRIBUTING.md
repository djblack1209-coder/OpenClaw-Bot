# Contributing to Kiro Gateway

Thanks for your interest in contributing!

## Philosophy

Kiro Gateway is a **transparent proxy** - we fix API-level issues while preserving user intent. When solving problems, we build systems that handle entire classes of issues, not one-off patches. We test paranoidly (happy path + edge cases + error scenarios), write clean code (type hints, docstrings, logging), and make errors actionable for users.

## Getting Started

1. Fork and clone the repo
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and configure
4. Run tests: `pytest -v`

## Development Workflow

```bash
# Create a branch
git checkout -b fix/your-fix
# or
git checkout -b feat/your-feature

# Make changes and test
pytest -v

# Commit (Conventional Commits format)
git commit -m "fix(scope): description"

# Push and open PR
git push origin your-branch
```

## Standards

- **Tests required** - Every commit must include comprehensive tests
- **Type hints** - All functions must be typed
- **Docstrings** - Google style with Args/Returns/Raises
- **Logging** - Use loguru at key decision points
- **Error handling** - Catch specific exceptions, add context
- **No tech debt** - Clean up hardcoded values and duplication immediately

## Pull Requests

**Before submitting:**
- Tests pass (including edge cases)
- Code follows project style
- Error messages are user-friendly
- No placeholders or TODOs
- Changes are focused. Don't mix functional changes with mass formatting/whitespace fixes across many files

**PR should include:**
- Clear description of what and why
- Link to related issue
- Test coverage summary

**Keep it reviewable:**
- If fixing formatting, limit it to files you're actually changing
- Avoid auto-formatter changes across the entire codebase in the same PR as functional changes

## CLA

All contributors must sign the Contributor License Agreement (automated via bot).

## Questions?

- **Bug reports:** [Open an issue](https://github.com/jwadow/kiro-gateway/issues)
- **Feature ideas:** Discuss in an issue first
- **Questions:** [Start a discussion](https://github.com/jwadow/kiro-gateway/discussions)

## Recognition

Contributors are listed in [`CONTRIBUTORS.md`](CONTRIBUTORS.md).

---

**For detailed guidelines:** See [`AGENTS.md`](AGENTS.md)
