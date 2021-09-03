

class Locale:
    """
    Encapsulates project directory structure and paths
    peculiar to the machine wielder is running on.
    """

    def __init__(
            self, project_root, super_project_root, super_project_name, module_root, code_repo_name, datastores_root,
            provision_root='unknown', packing_root='unknown', image_root='unknown', wield_root='unknown',
            code_root='unknown'
    ):
        """
        An opinionated convention based directory layout scheme for complex super repositories of
        Devops, Code, Development Wield projects
        :param project_root: The wielder project wrapping CICD of code
        :param super_project_root: The super project containing the wielder project and code projects
        :param super_project_name:
        :param module_root: The local Path to service CICD module
        :param code_repo_name: The local Path to service code module
        :param datastores_root: 3rd party datastore CICD path
        :param provision_root: The root of cloud resource allocation code (Terraform Ansible etc root)
        :param packing_root: The root of a directory used for dealing with code build and artifacts
        :param image_root: The root of the container docker files
        :param wield_root: The parent directory to the super repository, packing_root and local bucket simulation root
        :param code_root: The root of the code repository
        """

        self.project_root = project_root
        self.super_project_root = super_project_root
        self.super_project_name = super_project_name
        self.module_root = module_root
        self.code_repo_name = code_repo_name
        self.datastores_root = datastores_root
        self.provision_root = provision_root
        self.packing_root = packing_root
        self.image_root = image_root
        self.wield_root = wield_root
        self.code_root = code_root




