from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
      name='wielder',
      version='0.2.1',
      description='A reactive debuggable CI-CD & orchestration management tool'
                  ' for local & cloud deployments e.g. kubernetes, airflow & data lakes',
      long_description=long_description,
      long_description_content_type="text/markdown",
      url='https://github.com/hamshif/Wielder.git',
      download_url='https://github.com/hamshif/Wielder/archive/v0.2-beta.tar.gz',
      author='Hamshif',
      author_email='hamshif@gmail.com',
      license='Apache License Version 2.0',
      packages=find_packages(),
      zip_safe=False,
      install_requires=['Cython', 'gitpython', 'pyyaml', 'kubernetes', 'rx', 'jprops', 'pyhocon', 'requests'],
      keywords=['CI-CD', 'Kubernetes', 'Reactive'],
      classifiers=[
            'Development Status :: 4 - Beta',
            'Intended Audience :: Developers',
            'Topic :: Software Development :: Build Tools',
            'License :: OSI Approved :: MIT License',
            'Programming Language :: Python :: 3',
            'Programming Language :: Python :: 3.7',
      ],
)
