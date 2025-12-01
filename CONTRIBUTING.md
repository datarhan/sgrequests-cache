# Contributing to sgrequests-cache

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/yourusername/sgrequests-cache.git`
3. Create a virtual environment: `python -m venv venv`
4. Activate it: `source venv/bin/activate` (Unix) or `venv\Scripts\activate` (Windows)
5. Install dependencies: `pip install -e ".[dev]"`

## Development Workflow

1. Create a new branch: `git checkout -b feature/your-feature-name`
2. Make your changes
3. Run tests: `pytest`
4. Run linting: `black . && flake8`
5. Commit your changes: `git commit -m "Description of changes"`
6. Push to your fork: `git push origin feature/your-feature-name`
7. Create a Pull Request

## Code Style

- Follow PEP 8 guidelines
- Use Black for code formatting (line length: 100)
- Add type hints where possible
- Write docstrings for public APIs
- Keep functions focused and small

## Testing

- Write tests for new features
- Ensure all tests pass before submitting PR
- Aim for high test coverage
- Test with real-world scenarios when possible

## Pull Request Guidelines

- Provide clear description of changes
- Reference related issues
- Include tests for new features
- Update documentation if needed
- Ensure CI passes

## Reporting Issues

- Use GitHub Issues
- Provide clear description
- Include reproduction steps
- Share relevant logs/errors
- Specify your environment

## Questions?

Feel free to open an issue for questions or discussions.

Thank you for contributing! 🎉
