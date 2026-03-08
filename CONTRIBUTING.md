# Contributing to Alexandria-MIVP

Thank you for your interest in contributing to Alexandria Protocol + MIVP integration! This document provides guidelines for contributing to this project.

## Code of Conduct

Please read our [Code of Conduct](CODE_OF_CONDUCT.md) before participating.

## How Can I Contribute?

### Reporting Bugs
- Use the **Bug Report** issue template
- Include steps to reproduce, expected vs actual behavior
- Provide system information (OS, Python version, etc.)
- Include error messages and stack traces

### Suggesting Enhancements
- Use the **Feature Request** issue template
- Clearly describe the enhancement and use case
- Explain why this enhancement would be useful
- Consider if it aligns with project goals

### Code Contributions
1. **Fork** the repository
2. **Clone** your fork: `git clone https://github.com/YOUR_USERNAME/Alexandria-MIVP.git`
3. **Create a branch**: `git checkout -b feature/your-feature-name`
4. **Make changes** following our coding standards
5. **Test** your changes thoroughly
6. **Commit** with descriptive messages
7. **Push** to your fork: `git push origin feature/your-feature-name`
8. **Open a Pull Request**

## Development Setup

### Prerequisites
- Python 3.8+
- Git
- (Optional) Virtual environment

### Installation for Development
```bash
# Clone the repository
git clone https://github.com/hstre/Alexandria-MIVP.git
cd Alexandria-MIVP

# Install in development mode
pip install -e .

# Run tests
python -m pytest tests/
```

### Project Structure
```
alexandria-mivp/
├── src/                    # Core implementation
│   ├── __init__.py
│   ├── alexandria_v2.py   # Alexandria Protocol implementation
│   └── ...                # Other core modules
├── tests/                 # Test suite
├── examples/              # Usage examples
├── docs/                  # Documentation
└── setup.py              # Package configuration
```

## Coding Standards

### Python Style
- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/)
- Use 4-space indentation (no tabs)
- Maximum line length: 88 characters (Black compatible)
- Use descriptive variable names
- Include docstrings for public functions/classes

### Documentation
- All public APIs must have docstrings
- Use Google-style docstring format:
  ```python
  def function_name(param1, param2):
      """Short description.
      
      Args:
          param1: Description of param1
          param2: Description of param2
          
      Returns:
          Description of return value
          
      Raises:
          ExceptionType: When and why
      """
  ```
- Update documentation when changing APIs

### Testing
- Write tests for new functionality
- Maintain or improve test coverage
- Use pytest for testing
- Tests should be independent and idempotent

### Commit Messages
Use conventional commit format:
```
type(scope): brief description

Longer description if needed

BREAKING CHANGE: description of breaking changes
Footer: references, fixes, etc.
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Test changes
- `chore`: Maintenance tasks

**Examples:**
```
feat(alexandria): add support for audit decay tracking
fix(mivp): correct hash computation for empty policies
docs: update getting started guide with examples
```

## Pull Request Process

1. **Ensure** your code passes all tests
2. **Update** documentation for changed functionality
3. **Add** tests for new features
4. **Follow** the commit message format
5. **Link** related issues in the PR description
6. **Request review** from maintainers

### PR Review Checklist
- [ ] Code follows project standards
- [ ] Tests pass
- [ ] Documentation updated
- [ ] No breaking changes (or clearly marked)
- [ ] Changes are minimal and focused

## Security Considerations

### Cryptography
- Never modify cryptographic primitives without review
- Report security vulnerabilities privately (see Security Policy)
- Follow MIVP v2.1 specification precisely

### Identity Verification
- MIVP identity verification must remain tamper-proof
- Any changes to hash computation require thorough review
- Audit trails must maintain integrity

## Community Contributions

### Documentation
- Fix typos or clarify explanations
- Add examples or tutorials
- Translate documentation
- Improve API documentation

### Examples
- Create new usage examples
- Demonstrate integration with other systems
- Show real-world use cases

### Testing
- Add test cases for edge cases
- Improve test coverage
- Create integration tests

## Getting Help

### Questions & Discussions
- Use GitHub Discussions for questions
- Check existing issues before creating new ones
- Be respectful and constructive

### Mentoring
New contributors are welcome! Look for issues tagged:
- `good-first-issue`
- `help-wanted`
- `documentation`

## Recognition

Contributors will be acknowledged in:
- Release notes
- Contributors.md file
- Project documentation

---

Thank you for contributing to epistemic consistency and cryptographic identity verification for autonomous agents!