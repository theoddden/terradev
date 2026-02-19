#!/usr/bin/env python3
"""
Setup script for Terradev CLI
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_file.exists():
    requirements = requirements_file.read_text().strip().split("\n")
    requirements = [
        req.strip() for req in requirements if req.strip() and not req.startswith("#")
    ]

setup(
    name="terradev-cli",
    version="2.9.2",
    author="Terradev Team",
    author_email="team@terradev.com",
    description="Real multi-cloud GPU arbitrage — provision across 9 clouds in parallel",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/theoddden/terradev",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: Other/Proprietary License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Systems Administration",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
    ],
    python_requires=">=3.9",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=22.0.0",
            "flake8>=5.0.0",
            "mypy>=1.0.0",
            "pre-commit>=2.20.0",
        ],
        "docs": [
            "sphinx>=5.0.0",
            "sphinx-rtd-theme>=1.0.0",
            "myst-parser>=0.18.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "terradev=terradev_cli.cli:cli",
        ],
    },
    include_package_data=True,
    package_data={
        "terradev_cli": [
            "templates/*.yaml",
            "templates/*.json",
            "config/*.json",
        ],
    },
    zip_safe=False,
    keywords=[
        "cloud",
        "compute",
        "gpu",
        "provisioning",
        "optimization",
        "multi-cloud",
        "parallel",
        "cost-savings",
        "aws",
        "gcp",
        "azure",
        "machine-learning",
        "ai",
        "infrastructure",
    ],
    project_urls={
        "Bug Reports": "https://github.com/terradev/terradev-cli/issues",
        "Source": "https://github.com/terradev/terradev-cli",
        "Documentation": "https://docs.terradev.com",
        "Changelog": "https://github.com/terradev/terradev-cli/blob/main/CHANGELOG.md",
    },
)
