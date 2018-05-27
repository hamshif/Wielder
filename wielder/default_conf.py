
conf_file = 'default'
# conf_file = '/Users/gbar/stam/rtp/RtpKube/deploy/rxkube/conf/gcp_full_single_node_conf_poc.py'
# conf_file = '/Users/gbar/stam/rtp/RtpKube/deploy/rxkube/conf/minikube_full_single_node_conf.py'
# conf_file = '/Users/gbar/stam/rtp/RtpKube/deploy/rxkube/conf/gcp_full_single_node_conf_dev.py'
# conf_file = '/Users/gbar/stam/rtp/RtpKube/deploy/rxkube/conf/minikube_full_single_node_stateful_conf.py'
# conf_file = '/Users/gbar/stam/rtp/RtpKube/deploy/rxkube/conf/gcp_full_stateful_double_pod_conf_dev.py'


class Conf:

    def attr_list(self, should_print=False):

        items = self.__dict__.items()
        if should_print:
            [print(f"attribute: {k}    value: {v}") for k, v in items]

        return items


# TODO get conf fields from yaml not from python
def get_conf():

    if conf_file == 'default':

        conf = Conf()

        conf.conf_file = conf_file
        conf.deploy_env = 'local'
        conf.enable_debug = True
        conf.enable_dev = False
        conf.deploy_strategy = 'lean'
        conf.supported_deploy_envs = ['local', 'dev', 'int']

        conf.kube_context = 'minikube'

        # GCP
        conf.cloud_provider = 'gcp'
        conf.gcp_image_repo_zone = 'eu.gcr.io'
        conf.gcp_project = 'rtp-gcp-poc'

        conf.predictive_env = translate_to_predictive_env(conf.deploy_env)

        # ---------- Templates --------------

        conf.template_ignore_dirs = ['.git', '.terraform', 'rxkube', 'image', 'terra', 'db_scripts', 'sso_db',
                                     'bash-scripts', '__pycache__', 'debug-mount', 'artifacts', 'handy-scripts',
                                     'darwin_amd64', 'plugins', 'bucket'
                                     ]

        # TODO change rtpmaster as redis master
        conf.template_variables = [

            ('#kube_context#', conf.kube_context),
            ('#deploy_env#', conf.deploy_env),
            ('#DEV_MODE#', f"{conf.enable_dev}"),
            ('#predictive_env#', conf.predictive_env),

            ('#rtp_mysql_image#', 'rtp-mysql:dev'),

            ('#redis_master_cep#', 'rtpmaster'),
            ('#redis_master_dx#', 'rtpmaster'),
            ('#redis_master_lookup#', 'rtpmaster'),

            ('#rtp_redis_image#', 'rtp-redis:dev'),
            ('#rtp_redis_volume_name#', 'redis-pv-storage'),

            ('#rtp_mongo_image#', f"mongo:3.2"),

            ('#rtp_sso_image#', f"rtp/sso:dev"),
            ('#rtp_dx_image#', f"rtp/dx:dev"),
            ('#rtp_cep_image#', f"rtp/cep:dev"),
            ('#rtp_backoffice_image#', f"rtp/backoffice:dev"),



            ('#dx_name#', f"dx"),
            ('#dx_mount_name#', f"DX"),
            ('#dx_node_port#', "30300"),
            ('#dx_debug_port#', "30301"),

            ('#cep_name#', f"cep"),
            ('#cep_mount_name#', f"CEP"),
            ('#cep_node_port#', "30200"),
            ('#cep_h2_node_port#', "30201"),
            ('#cep_debug_port#', "30202"),

            ('#sso_name#', f"sso"),

            ('#sso_mount_name#', f"SSO"),
            ('#sso_node_port#', "30120"),
            ('#sso_debug_port#', "30121"),

            ('#backoffice_name#', f"backoffice"),
            ('#backoffice_mount_name#', f"BO"),
            ('#backoffice_node_port#', "30100"),
            ('#backoffice_debug_port#', "30101"),

            ('#DX_ENABLED#', 'true'),

            ('#SMTP_HOST#', 'sjqemtavip.marketo.org'),

            ('#EXPORT_S3_ENABLE#', 'true'),
            ('#S3_RCMD_RES_BUCKET#', 'ie-emr-output-prod'),
            ('#S3_RCMD_RAW_BUCKET#', 'ie-emr-rawdata-prod'),

            ('#EXPORT_HDFS_ENABLE#', 'false'),
            ('#EXPORT_HDFS_URL#', '127.0.0.1'),
            ('#EXPORT_HDFS_PORT#', '50070'),
            ('#EXPORT_HDFS_HOME#', '/apps/rtp/'),
            ('#EXPORT_HDFS_AUTH_METHOD#', 'SIMPLE'),
            ('#EXPORT_HDFS_KERBEROS_PRINCIPAL#', 'rtp-qe@SJHDPINT.MARKETO.ORG'),
            ('#EXPORT_HDFS_HA_ENABLED#', 'true'),
            ('#EXPORT_HDFS_NAME_SERVICES#', 'mkto'),

            ('#EXPORT_HDFS_NODE1_ADDRESS#', 'sjhdp-intnn1.marketo.org'),
            ('#EXPORT_HDFS_NODE2_ADDRESS#', 'sjhdp-intnn2.marketo.org'),
            ('#EXPORT_HDFS_NODE1_NAME#', 'nn1'),
            ('#EXPORT_HDFS_NODE2_NAME#', 'nn2'),

            ('#RCMD_SOURCE_INPUT#', 'S3'),

            ('#RCMD_ALGO_POPULAR_PREP#', 'true'),
            ('#RCMD_ALGO_TREND_PREP#', 'true'),

            ('#RCMD_SFO_REFRESH#', '3600000'),
            ('#RCMD_ITEMBASED_REFRESH#', '3600000'),

            ('#RML_ENABLED#', 'true'),
            ('#RML_HOST#', f"sjint-tsdb-vip.marketo.org"),


            ('#KAFKA_TOPIC#', 'rtpactivities.sjrtpint'),
            ('#KAFKA_BROKER#', 'sjkafka-int1.marketo.org:6667,sjkafka-int2.marketo.org:6667,sjkafka-int3.marketo.org:6667,sjkafka-int4.marketo.org:6667,sjkafka-int5.marketo.org:6667'),
            ('#ZOOKEEPER_SERVERS#', 'sjhdp-intzkobsrv1.marketo.org:2181,sjhdp-intzkobsrv2.marketo.org:2181'),
            ('#SCHEMA_REGISTRY_URL#', 'http://int-schemareg-ws.marketo.org'),

            ('#RCMD_NAIVEBAYES_REFRESH#', '3600000'),

            ('#ESP_EXPORT_ENABLED#', 'true'),
            ('#ESP_EXPORT_RCMD_ENABLED#', 'true'),
            ('#ESP_EXPORT_ACTIVE_STORAGE_EXECUTOR#', 'ALL'),
            ('#ESP_EXPORT_ACTIVE_STORAGE_READER#', 'GCP'),
            ('#ESP_EXPORT_GCS_CREDENTIALS_FILE#', 'marketo-contentai-dev.json'),
            ('#GCS_RCMD_RES_BUCKET#', 'ie-emr-output-prod'),

        ]

        # ---------- Scripts --------------

        conf.script_variables = {
            # MySQL
            'trw_password': 'teyhc100',
            'sso_password': '',


            'rtp_mongo_admin': 'main_admin',
            'rtp_mongo_password': 'abc123',
            'rtp_mongo_number_of_replicas': 1,
        }

        return conf

    else:

        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("conf", conf_file)
        non_default_conf = module_from_spec(spec)
        spec.loader.exec_module(non_default_conf)

        conf = Conf()
        conf.conf_file = conf_file
        conf = non_default_conf.fill_alternate_conf(conf)

        return conf


# TODO get this from yaml it should be an interface
def translate_to_predictive_env(deploy_env):

    _env = deploy_env

    if deploy_env == 'local' or deploy_env == 'int':

        _env = 'dev'

    if deploy_env == 'qa':

        _env = 'qe'

    return _env