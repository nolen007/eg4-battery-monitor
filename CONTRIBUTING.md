# Contributing to EG4 Battery Monitor

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/yourusername/eg4-battery-monitor.git
   cd eg4-battery-monitor
   ```

3. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate     # Windows
   ```

4. Install development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

5. Install pre-commit hooks:
   ```bash
   pre-commit install
   ```

## Development Workflow

### Code Style

This project uses:
- **Black** for code formatting
- **Ruff** for linting
- **MyPy** for type checking

Run all checks:
```bash
black src tests
ruff check src tests
mypy src
```

### Testing

Run tests with pytest:
```bash
pytest
pytest --cov=eg4_monitor --cov-report=html
```

### Commit Messages

Use clear, descriptive commit messages:
- `feat: Add support for multiple batteries`
- `fix: Handle connection timeout gracefully`
- `docs: Update README with Docker instructions`
- `refactor: Simplify MQTT publishing logic`

## Adding Support for New Batteries

If you want to add support for a different EG4 battery model:

1. Create a new register map in `src/eg4_monitor/battery.py`
2. Add any model-specific parsing logic
3. Update the documentation
4. Add tests for the new model

## Pull Request Process

1. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes and commit them

3. Ensure all tests pass:
   ```bash
   pytest
   ```

4. Push to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

5. Open a Pull Request with:
   - Clear description of changes
   - Any relevant issue numbers
   - Screenshots (if UI changes)

## Reporting Issues

When reporting issues, please include:

1. **Environment**: OS, Python version, battery model
2. **Steps to reproduce**: What commands did you run?
3. **Expected behavior**: What should happen?
4. **Actual behavior**: What actually happened?
5. **Logs**: Any error messages or debug output

## Feature Requests

Feature requests are welcome! Please:

1. Check if the feature already exists or is planned
2. Open an issue with the `enhancement` label
3. Describe the use case and expected behavior

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
