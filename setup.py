from setuptools import setup, find_packages

_version = '0.5.0'

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='wielder',
    version=_version,
    description='A reactive debuggable CI-CD & orchestration management tool'
                ' for local & cloud deployments e.g. kubernetes, airflow & data lakes',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/hamshif/Wielder.git',
    download_url=f'https://github.com/hamshif/Wielder/archive/v{_version}-beta.tar.gz',
    author='Hamshif',
    author_email='hamshif@gmail.com',
    license='Apache License Version 2.0',
    packages=find_packages(),
    zip_safe=False,
    install_requires=[
        'wheel', 'Cython', 'GitPython', 'PyYAML', 'kubernetes', 'rx==3.2.0', 'jprops',
        'pyhocon', 'requests', 'deepdiff', 'botocore', 'boto3', 'tabulate',
        'kazoo', 'kafka', 'confluent-kafka', 'google-api-python-client', 'google-auth-oauthlib',
        'cassandra-driver',
        # TODO use the next version of cassandra driver supporting up to Python 3.11
    ],
    keywords=['CI-CD', 'Kubernetes', 'Reactive'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
    ],
)
