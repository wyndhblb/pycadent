# coding: utf-8
from setuptools import setup

setup(
    name='cadent',
    version='0.0.12',
    url='https://github.com/wyndhblb/pycadent',
    license='Apache 2',
    author=u'Bo Blanton',
    author_email='bo.blanton@gmail.com',
    description=('A plugin for using graphite-web/graphite-api with the '
                 'Cadent storage backend'),
    long_description=open('README.md').read(),
    packages=('cadent', 'cadent/pb',),
    zip_safe=False,
    include_package_data=True,
    platforms='any',
    classifiers=(
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: System :: Monitoring',
    ),
    install_requires=(
        'requests', 'msgpack-python', 'protobuf',
    ),
)
