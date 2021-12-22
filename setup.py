#!/usr/bin/env python3
from setuptools import setup

from pathlib import Path
this_directory = Path(__file__).parent
long_description = (this_directory / 'README.md').read_text()

repo_url = 'https://github.com/atodekangae/pydetour'

setup(
    name='pydetour',
    py_modules=['pydetour'],
    version='0.1.0',
    url=repo_url,
    author='atodekangae',
    author_email='atodekangae@gmail.com',
    description='Redirect any callable objects in Python, by manipulating tp_vectorcall of a PyObject with ctypes',
    long_description=long_description,
    long_description_content_type='text/markdown',
    python_requires='>=3.8',
    keywords=['ctypes', 'detour', 'hook'],
    project_urls={
        'Source': repo_url,
    },
    classifiers=[
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
    ]
)
