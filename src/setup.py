from setuptools import setup, find_packages

setup(name='wielder',
      version='0.1',
      description='A reactive debuggable orchestration management tool for cloud'
                  'such as kubernetes deployments and datalakes',
      url='https://github.com/hamshif/Wielder.git',
      author='gbar',
      author_email='gbar@marketo.com',
      license='MIT',
      packages=find_packages(),
      zip_safe=False,
      install_requires=['kubernetes', 'jprops']
      )
