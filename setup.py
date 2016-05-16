from setuptools import setup


setup(
    name='zplgrf',
    version = '1.0',
    description = 'Tools to work with ZPL GRF images and CUPS',
    author = 'Kyle MacFarlane',
    author_email = 'kyle@deletethetrees.com',
    url = 'https://github.com/kylemacfarlane/zplgrf',
    packages = ['zplgrf'],
    install_requires = [
        'setuptools',
        'pillow'
    ],
    test_suite='tests',
    classifiers = [
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5'
    ]
)
