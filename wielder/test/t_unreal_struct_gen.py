import logging

from wielder.unreal.struct_gen import *
from wielder.util.log_util import setup_logging
from wielder.wield.project import default_conf_root, get_super_project_wield_conf, DEFAULT_WIELDER_APP


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    project_conf_dir = default_conf_root()

    conf = get_super_project_wield_conf(project_conf_dir, app=DEFAULT_WIELDER_APP, configure_wield_modules=True)

    uconf = conf.unreal
    # Delete old structs
    solution_name = uconf.solution_name

    if uconf.del_structs:
        delete_old_structs(solution_name, uconf.project_path)

    # Define the path to your config file
    conf_path = uconf.conf_path
    # Define the output directory
    output_dir = uconf.struct_path
    # Generate the struct code
    generate_structs(conf_path, output_dir)

    # Prepare Unreal for building
    #

    # Generate Visual Studio project files
    if uconf.build:
        if os.name == 'nt':
            prep_unreal_build(solution_name, uconf.project_path)

            unreal_dir = f"{conf.staging_root}\\dev\\UE_5.2"
            generate_vs_proj_files(solution_name, unreal_dir, uconf.project_path)

            # # Build the project with Visual Studio
            vs_dir = "\"C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\MSBuild\\Current\\Bin\\MSBuild.exe\""
            solution_path = os.path.join(uconf.project_path, f"{solution_name}.sln")
            build_unreal_proj(vs_dir, solution_path)
