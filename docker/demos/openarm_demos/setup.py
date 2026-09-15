from setuptools import setup
setup(name='openarm_demos', version='0.1.0', packages=['openarm_demos'],
      data_files=[('share/ament_index/resource_index/packages',['resource/openarm_demos']),('share/openarm_demos',['package.xml'])],
      install_requires=['setuptools'], zip_safe=True,
      entry_points={'console_scripts':['grasp_demo = openarm_demos.grasp_demo:main','bimanual_demo = openarm_demos.bimanual_demo:main']})
