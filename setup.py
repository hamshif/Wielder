from setuptools import setup, find_packages

_version = '0.3.0'

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
    install_requires=['Cython==0.29.24', 'GitPython==3.1.18', 'PyYAML==5.4.1', 'kubernetes==17.17.0', 'Rx==3.2.0',
                      'jprops==2.0.2', 'pyhocon==0.3.58', 'requests==2.26.0', 'deepdiff==6.2.1',
                      'botocore==1.21.21', 'boto3==1.18.21'],
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
