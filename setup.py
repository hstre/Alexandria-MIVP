from setuptools import setup, find_packages

# Kept for legacy tools; authoritative config is in pyproject.toml.
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="alexandria-mivp",
    version="0.1.0",
    author="H.-Steffen Rentschler",
    author_email="tentschler@lbsmail.de",
    description=(
        "Binding claims to declared, hash-addressed model/policy/runtime "
        "profiles with epistemic consistency"
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/hstre/Alexandria-MIVP",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    install_requires=[],
    extras_require={
        "signatures": ["cryptography>=42.0.0"],
        "s3":         ["boto3>=1.26.0"],
        "ipfs":       ["requests>=2.28.0"],
        "dev":        ["pytest>=7.0.0", "black>=23.0.0", "mypy>=1.0.0"],
        "all":        ["cryptography>=42.0.0", "boto3>=1.26.0", "requests>=2.28.0"],
    },
)
