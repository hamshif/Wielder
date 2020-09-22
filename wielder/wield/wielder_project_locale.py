

class Locale:
    """
    Encapsulates project directory structure and paths
    peculiar to the machine wielder is running on.
    """

    def __init__(self, project_root, super_project_root, module_root, code_path, datastores_root,
                 provision_root='unknown'):
        """

        :param project_root: The wielder project wrapping CICD of code
        :param super_project_root: The super project containing the wielder project and code projects
        :param module_root: The local Path to service CICD module
        :param code_path: The local Path to service code module
        :param datastores_root: 3rd party datastore CICD path
        :param provision_root: provision (Terraform root)
        """

        self.project_root = project_root
        self.super_project_root = super_project_root
        self.module_root = module_root
        self.code_path = code_path
        self.datastores_root = datastores_root
        self.provision_root = provision_root




