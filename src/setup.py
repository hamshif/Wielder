from setuptools import setup, find_packages

setup(name='wielder',
      version='0.1',
      description='A reactive debuggable CICD & orchestration management tool'
                  ' for local & cloud deployments e.g. kubernetes, airflow & data lakes',
      url='https://github.com/hamshif/Wielder.git',
      author='gbar',
      author_email='hamshif@gmail.com',
      license='MIT',
      packages=find_packages(),
      zip_safe=False,
      install_requires=['kubernetes', 'jprops']
      )
