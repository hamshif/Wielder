import json
import os
import subprocess

# MAKE SURE THAT VISUAL STUDIO AND UNREAL ENGINE ARE CLOSED PRIOR TO RUNNING!
# THIS SCRIPT ASSUMES A WINDOWS ENVIRONMENT!

# Map pyspark types to Unreal types
pyspark_cpp_type_mapping = {
    "int": "int32",
    "integer": "int32",
    "float": "float",
    "string": "FString",
    "bool": "bool",
    "double": "double",
    "long": "int32",  # Unreal does not support int64. We may need to be careful with this.
    "short": "int32"
    # Add more types here as needed
}


def delete_old_structs(solution_name: str, unreal_project_dir: str):
    """
    Deletes all files in the Source directory ending in 'TempStruct.cpp' and 'TempStruct.h'
    :param solution_name:
    :param unreal_project_dir:
    :return:
    """
    # Get the path to the Source directory
    source_dir = os.path.join(unreal_project_dir, "Source", solution_name)
    # Iterate over all files in the Source directory
    for root, dirs, files in os.walk(source_dir):
        for file in files:
            # If the file ends in 'TempStruct.cpp' or 'TempStruct.h', delete it
            if file.endswith("TempStruct.cpp") or file.endswith("TempStruct.h"):
                os.remove(os.path.join(root, file))


def generate_structs(config_file_path: str, output_dir: str):
    with open(config_file_path, 'r') as f:
        data = json.load(f)

    # Iterate over main datasets
    for main_dataset_name in data['data_types']:
        main_dataset = data['data_types'][main_dataset_name]

        # Iterate over sub-datasets
        for sub_dataset_name in main_dataset["tables"]:
            sub_dataset = main_dataset["tables"][sub_dataset_name]
            properties = sub_dataset['columns']

            struct_name = (f"{main_dataset_name.capitalize()}_{sub_dataset_name.capitalize()}_Temp_Struct")
            # Get rid of all underscores in the name and capitalize the first letter of each word
            struct_name = struct_name.replace("_", " ").title().replace(" ", "")
            # Write code for the header
            header_code = f"#pragma once\n\n#include \"CoreMinimal.h\"\n#include \"Engine/DataTable.h\"\n#include \"{struct_name}.generated.h\"\n\nUSTRUCT(BlueprintType)\nstruct F{struct_name} : public FTableRowBase\n{{\n    GENERATED_BODY()\n\npublic:\n"
            # Iterate through the properties and write code for each one
            ignored_first_col = False
            for prop in properties:
                # Ignore the first property, which is an indexing column
                if not ignored_first_col:
                    ignored_first_col = True
                    print("Ignored col: ", prop['name'])
                    continue
                unreal_type = pyspark_cpp_type_mapping.get(prop['type'], "UNKNOWN_TYPE")
                header_code += f"    UPROPERTY(EditAnywhere, BlueprintReadWrite)\n    {unreal_type} {prop['name']};\n\n"
            header_code += "};\n"
            # Write code for the .cpp file
            cpp_code = f'#include "{struct_name}.h"\n'
            # Write the header code to the header file
            dest = f"{struct_name}.h"
            print("Writing to: ", os.path.join(output_dir, dest))
            with open(os.path.join(output_dir, dest), 'w') as f:
                f.write(header_code)
            # Write the .cpp code to the .cpp file
            dest = f"{struct_name}.cpp"
            print("Writing to: ", os.path.join(output_dir, dest))
            with open(os.path.join(output_dir, dest), 'w') as f:
                f.write(cpp_code)
            print(f"{struct_name} header and .cpp code written to {os.path.abspath(output_dir)}")


def prep_unreal_build(solution_name: str, unreal_proj_dir: str):
    """
    Deletes folders like Binaries, Intermediate, Saved, DerivedDataCache, and .vs.
    :param solution_name:
    :param unreal_proj_dir:
    :return:
    """
    # Open the project directory
    for root, dirs, files in os.walk(unreal_proj_dir):
        # Iterate over all directories
        for dir in dirs:
            # If the directory name is one of the ones we want to delete
            if dir in ["Binaries", "Intermediate", "Saved", "DerivedDataCache", ".vs"]:
                # Delete everything in the directory and suppress output
                os.system(f"del /F /S /Q {os.path.join(root, dir)} 1>nul")
                # Delete the directory, even if it's not empty
                os.system(f"rmdir /S /Q {os.path.join(root, dir)}")
                print(f"Deleted {os.path.join(root, dir)}")
        # Iterate over all files
        for file in files:
            # If the file name is one of the ones we want to delete
            if file in [f"{solution_name}.sln", f"{solution_name}.vcxproj", f"{solution_name}.vcxproj.filters"]:
                # Delete the file
                os.remove(os.path.join(root, file))
                print(f"Deleted {os.path.join(root, file)}")


def generate_vs_proj_files(solution_name: str, unreal_dir: str, unreal_project_dir: str):
    """
    For windows platform only.
    Generates the Visual Studio project files for this Unreal project
    :param solution_name:
    :param unreal_dir:
    :param unreal_project_dir:
    :return:
    """
    # Generate the VS project files
    build_tool_path = os.path.join(unreal_dir, "Engine\\Binaries\\DotNET\\UnrealBuildTool\\UnrealBuildTool.dll")
    uproject_file_path = os.path.join(unreal_project_dir, f"{solution_name}.uproject")
    # The command to generate Visual Studio project files
    command = [
        "dotnet",
        build_tool_path,
        "-projectfiles",
        "-project=" + uproject_file_path,
        "-game",
        "-rocket",
        "-progress",
    ]
    # Run the command
    subprocess.run(command)


def build_unreal_proj(vs_dir: str, solution_path: str):
    """
    For windows platform only.
    :param vs_dir:
    :param solution_path:
    :return:
    """
    command = f"{vs_dir} {solution_path} /property:Configuration=Development /property:Platform=Win64 /verbosity:detailed"
    print(command)
    subprocess.call(command, shell=True)
