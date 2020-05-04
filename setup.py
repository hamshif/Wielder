from setuptools import setup, find_packages

setup(
      name='wielder',
      version='0.1',
      description='A reactive debuggable CI-CD & orchestration management tool'
                  ' for local & cloud deployments e.g. kubernetes, airflow & data lakes',
      url='https://github.com/hamshif/Wielder.git',
      download_url='https://github.com/hamshif/Wielder/archive/v0.1-beta.tar.gz',
      author='Hamshif',
      author_email='hamshif@gmail.com',
      license='Apache License Version 2.0',
      packages=find_packages(),
      zip_safe=False,
      install_requires=['gitpython', 'pyyaml', 'kubernetes', 'rx', 'jprops', 'pyhocon', 'requests'],
      keywords=['CI-CD', 'Kubernetes', 'Reactive'],
      classifiers=[
            'Development Status :: 4 - Beta',
            'Intended Audience :: Developers',
            'Topic :: Software Development :: CI-CD Tools',
            'License :: OSI Approved :: Apache License',
            'Programming Language :: Python :: 3',
            'Programming Language :: Python :: 3.6.5',
      ],
)
