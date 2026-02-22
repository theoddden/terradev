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
    version="3.1.2",
    author="Terradev Team",
    author_email="team@terradev.com",
    description="Cross-cloud GPU provisioning with GitOps automation and HuggingFace Spaces deployment",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/theoddden/terradev",
    packages=find_packages(),
    py_modules=["cli"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "terradev=cli:cli",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
