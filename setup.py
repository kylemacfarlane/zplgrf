import os
from setuptools import find_packages, setup


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name='rasterlabel',
    version='2.0.0',
    description=(
        'Convert PDFs and images to rasters for use with label printers'
    ),
    long_description=read('README.rst'),
    author='Kyle MacFarlane',
    author_email='kyle@deletethetrees.com',
    url='https://github.com/kylemacfarlane/rasterlabel',
    license='GPLv3',

    packages=find_packages('src'),
    package_dir={'': 'src'},
    install_requires=[
        'setuptools',
        'pillow'
    ],
    tests_require=[
        'ghostscript'
    ],
    extras_require={
        'bindings': ['ghostscript']
    },
    test_suite='rasterlabel.tests',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8'
    ]
)
