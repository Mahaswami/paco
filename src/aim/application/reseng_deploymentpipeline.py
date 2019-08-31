from aim import models, cftemplates
from aim.application.res_engine import ResourceEngine
from aim.core.yaml import YAML
from aim.models import schemas

yaml=YAML()
yaml.default_flow_sytle = False

class DeploymentPipelineResourceEngine(ResourceEngine):

    def __init__(self, app_engine):
        super().__init__(app_engine)

        self.grp_id = None
        self.res_id = None
        self.res_stack_tags = None
        self.pipeline_account_ctx = None
        self.pipeline_config = None
        self.kms_template = None
        self.kms_crypto_principle_list = []
        self.artifacts_bucket_policy_resource_arns = []
        self.artifacts_bucket_meta = {
            'ref': None,
            'arn': None,
            'name': None,
        }

        self.source_stage = None

    def init_stage(self, stage_config):
        for action_name in stage_config.keys():
            action_config = stage_config[action_name]
            action_config.resolve_ref_obj = self
            method_name = 'init_stage_action_' + action_config.type.replace('.', '_').lower()
            print("Loading DeploymentPipeline Stage: "+action_name+": {}".format(type(action_config)))
            method = getattr(self, method_name)
            method(action_config)

    def init_resource(self, grp_id, res_id, pipeline_config, res_stack_tags):
        self.grp_id = grp_id
        self.res_id = res_id
        self.pipeline_config = pipeline_config
        self.res_stack_tags = res_stack_tags

        self.pipeline_config.resolve_ref_obj = self

        self.pipeline_account_ctx = self.aim_ctx.get_account_context(pipeline_config.configuration.account)
        #data_account_ctx = self.aim_ctx.get_account_context("aim.ref accounts.data")

        # -----------------
        # S3 Artifacts Bucket:
        s3_ctl = self.aim_ctx.get_controller('S3')
        self.artifacts_bucket_meta['ref'] = pipeline_config.configuration.artifacts_bucket
        self.artifacts_bucket_meta['arn'] = s3_ctl.get_bucket_arn(self.artifacts_bucket_meta['ref'])
        self.artifacts_bucket_meta['name'] = s3_ctl.get_bucket_name(self.artifacts_bucket_meta['ref'])

        # ----------------
        # KMS Key
        #
        aws_account_ref = 'aim.ref ' + self.parent_config_ref + '.network.aws_account'
        # Application Account
        self.kms_crypto_principle_list.append("aim.sub 'arn:aws:iam::${%s}:root'" % (self.aim_ctx.get_ref(aws_account_ref)))
        # CodeCommit Account
        self.kms_crypto_principle_list.append("aim.sub 'arn:aws:iam::${aim.ref accounts.data}:root'")
        kms_config_dict = {
            'admin_principal': {
                'aws': [ "!Sub 'arn:aws:iam::${{AWS::AccountId}}:root'" ]
            },
            'crypto_principal': {
                'aws': self.kms_crypto_principle_list
            }
        }
        aws_name = '-'.join([grp_id, res_id])
        kms_config_ref = pipeline_config.aim_ref_parts + '.kms'
        self.kms_template = cftemplates.KMS(
            self.aim_ctx,
            self.pipeline_account_ctx,
            self.aws_region,
            self.stack_group,
            res_stack_tags,
            aws_name,
            pipeline_config,
            kms_config_ref,
            kms_config_dict
        )


        # Stages
        self.init_stage(pipeline_config.source)
        self.init_stage(pipeline_config.build)
        self.init_stage(pipeline_config.deploy)

        # CodePipeline
        codepipeline_config_ref = pipeline_config.aim_ref_parts + '.codepipeline'
        aws_name = '-'.join([grp_id, res_id])
        pipeline_config._template = cftemplates.CodePipeline(
            self.aim_ctx,
            self.pipeline_account_ctx,
            self.aws_region,
            self.stack_group,
            res_stack_tags,
            self.env_ctx,
            aws_name,
            self.app_id,
            grp_id,
            res_id,
            pipeline_config,
            self.artifacts_bucket_meta['name'],
            codepipeline_config_ref
        )


        # Add CodeBuild Role ARN to KMS Key principal now that the role is created
        kms_config_dict['crypto_principal']['aws'] = self.kms_crypto_principle_list
        aws_name = '-'.join([grp_id, res_id])
        kms_template = cftemplates.KMS(
            self.aim_ctx,
            self.pipeline_account_ctx,
            self.aws_region,
            self.stack_group,
            res_stack_tags,
            aws_name,
            pipeline_config,
            kms_config_ref,
            kms_config_dict
        )
        # Adding a file id allows us to generate a second template without overwritting
        # the first one. This is needed as we need to update the KMS policy with the
        # Codebuild Arn after the Codebuild has been created.
        kms_template.set_template_file_id("post-pipeline")

        # Get the ASG Instance Role ARN
        #asg_instance_role_ref = pipeline_config.asg+'.instance_iam_role.arn'
        #codebuild_role_ref = pipeline_config.aim_ref_parts + '.codebuild_role.arn'
        #codedeploy_tools_delegate_role_ref = pipeline_config.aim_ref_parts + '.codedeploy_tools_delegate_role.arn'
        #codecommit_role_ref = pipeline_config.aim_ref_parts + '.codecommit_role.arn'
        self.artifacts_bucket_policy_resource_arns.append("aim.sub '${%s}'" % (pipeline_config.aim_ref + '.codepipeline_role.arn'))
        cpbd_s3_bucket_policy = {
            'aws': self.artifacts_bucket_policy_resource_arns,
            #[
            #    "aim.sub '${{aim.ref {0}}}'".format(codebuild_role_ref),
            #    "aim.sub '${{aim.ref {0}}}'".format(codepipeline_role_ref),
            #    "aim.sub '${{aim.ref {0}}}'".format(codedeploy_tools_delegate_role_ref),
            #    "aim.sub '${{aim.ref {0}}}'".format(codecommit_role_ref),
            #    "aim.sub '${{{0}}}'".format(asg_instance_role_ref)
            #],
            'action': [ 's3:*' ],
            'effect': 'Allow',
            'resource_suffix': [ '/*', '' ]
        }
        s3_ctl.add_bucket_policy(self.artifacts_bucket_meta['ref'], cpbd_s3_bucket_policy)

    def init_stage_action_codecommit_source(self, action_config):
        # -------------------------------------------
        # CodeCommit Delegate Role
        role_yaml = """
assume_role_policy:
  effect: Allow
  aws:
    - '{0[tools_account_id]:s}'
instance_profile: false
path: /
role_name: CodeCommit
policies:
  - name: DeploymentPipeline
    statement:
      - effect: Allow
        action:
          - codecommit:BatchGetRepositories
          - codecommit:Get*
          - codecommit:GitPull
          - codecommit:List*
          - codecommit:CancelUploadArchive
          - codecommit:UploadArchive
        resource:
          - {0[codecommit_ref]:s}
      - effect: Allow
        action:
          - 's3:*'
        resource:
          - {0[artifact_bucket_arn]:s}
          - {0[artifact_bucket_arn]:s}/*
      - effect: Allow
        action:
          - 'kms:*'
        resource:
          - "!Ref CMKArn"
"""
        codecommit_ref = action_config.codecommit_repository
        role_table = {
            'codecommit_account_id': "aim.sub '${{{0}.account_id}}'".format(codecommit_ref),
            'tools_account_id': self.pipeline_account_ctx.get_id(),
            'codecommit_ref': "aim.sub '${{{0}.arn}}'".format(codecommit_ref),
            'artifact_bucket_arn': self.artifacts_bucket_meta['arn']
        }
        role_config_dict = yaml.load(role_yaml.format(role_table))
        codecommit_iam_role_config = models.iam.Role()
        codecommit_iam_role_config.apply_config(role_config_dict)
        codecommit_iam_role_config.enabled = action_config.is_enabled()

        iam_ctl = self.aim_ctx.get_controller('IAM')
        # The ID to give this role is: group.resource.instance_iam_role
        codecommit_iam_role_id = self.gen_iam_role_id(self.res_id, 'codecommit_role')
        self.artifacts_bucket_policy_resource_arns.append("aim.sub '${%s}'" % (action_config.aim_ref + '.codecommit_role.arn'))
        # IAM Roles Parameters
        iam_role_params = [
            {
                'key': 'CMKArn',
                'value': self.pipeline_config.aim_ref + '.kms.arn',
                'type': 'String',
                'description': 'DeploymentPipeline KMS Key Arn'
            }
        ]
        codecommit_account_ref = self.aim_ctx.get_ref(action_config.codecommit_repository+'.account')
        codecommit_account_ctx = self.aim_ctx.get_account_context(codecommit_account_ref)
        codecommit_iam_role_ref = '{}.codecommit_role'.format(action_config.aim_ref_parts)
        iam_ctl.add_role(
            aim_ctx=self.aim_ctx,
            account_ctx=codecommit_account_ctx,
            region=self.aws_region,
            group_id=self.grp_id,
            role_id=codecommit_iam_role_id,
            role_ref=codecommit_iam_role_ref,
            role_config=codecommit_iam_role_config,
            stack_group=self.stack_group,
            template_params=iam_role_params,
            stack_tags=self.res_stack_tags
        )

    # Code Deploy
    def init_stage_action_codedeploy_deploy(self, action_config):
        self.artifacts_bucket_policy_resource_arns.append("aim.sub '${%s}'" % (action_config.aim_ref + '.codedeploy_tools_delegate_role.arn'))
        self.artifacts_bucket_policy_resource_arns.append(self.aim_ctx.get_ref(action_config.auto_scaling_group+'.instance_iam_role.arn'))
        aws_name = '-'.join([self.grp_id, self.res_id])
        codedeploy_config_ref = action_config.aim_ref_parts
        action_config._template = cftemplates.CodeDeploy(
            self.aim_ctx,
            self.account_ctx,
            self.aws_region,
            self.stack_group,
            self.res_stack_tags,
            self.env_ctx,
            aws_name,
            self.app_id,
            self.grp_id,
            self.res_id,
            self.pipeline_config,
            action_config,
            self.artifacts_bucket_meta['name'],
            codedeploy_config_ref
        )

    def init_stage_action_codebuild_build(self, action_config):
        self.artifacts_bucket_policy_resource_arns.append("aim.sub '${%s}'" % (action_config.aim_ref + '.project_role.arn'))
        self.kms_crypto_principle_list.append("aim.sub '${%s}'" % (action_config.aim_ref+'.project_role.arn'))
        aws_name = '-'.join([self.grp_id, self.res_id])
        codebuild_config_ref = action_config.aim_ref_parts + '.codebuild.' + action_config.name
        action_config._template = cftemplates.CodeBuild(
            self.aim_ctx,
            self.pipeline_account_ctx,
            self.aws_region,
            self.stack_group,
            self.res_stack_tags,
            self.env_ctx,
            aws_name,
            self.app_id,
            self.grp_id,
            self.res_id,
            self.pipeline_config,
            action_config,
            self.artifacts_bucket_meta['name'],
            codebuild_config_ref
        )

    def init_stage_action_manualapproval_deploy(self, action_config):
        pass

    def resolve_ref(self, ref):
        if schemas.IDeploymentPipelineDeployCodeDeploy.providedBy(ref.resource):
            # CodeDeploy
            if ref.resource_ref == 'deployment_group.name':
                return ref.resource._template.stack
            elif ref.resource_ref == 'codedeploy_tools_delegate_role.arn':
                return ref.resource._template.get_tools_delegate_role_arn()
            elif ref.resource_ref == 'codedeploy_application_name':
                return ref.resource._template.get_application_name()
            elif ref.resource_ref == 'deployment_group.name':
                return ref.resource._template.stack
        elif schemas.IDeploymentPipeline.providedBy(ref.resource):
            # DeploymentPipeline
            if ref.resource_ref.startswith('kms.'):
                return self.kms_template.stack
            elif ref.resource_ref == 'codepipeline_role.arn':
                return ref.resource._template.get_codepipeline_role_arn()
        elif schemas.IDeploymentPipelineSourceCodeCommit.providedBy(ref.resource):
            # CodeCommit
            if ref.resource_ref == 'codecommit_role.arn':
                iam_ctl = self.aim_ctx.get_controller("IAM")
                return iam_ctl.role_arn(ref.raw[:-4])
            elif ref.resource_ref == 'codecommit.arn':
                codecommit_ref = ref.resource.codecommit_repository
                return self.aim_ctx.get_ref(codecommit_ref+".arn")
        elif schemas.IDeploymentPipelineBuildCodeBuild.providedBy(ref.resource):
            # CodeBuild
            if ref.resource_ref == 'project_role.arn':
                # self.cpbd_codepipebuild_template will fail if there are two deployments
                # this application... corner case, but might happen?
                return ref.resource._template.get_project_role_arn()
            elif ref.resource_ref == 'project.arn':
                # self.cpbd_codepipebuild_template will fail if there are two deployments
                # this application... corner case, but might happen?
                return ref.resource._template.get_project_arn()


        breakpoint()
        if ref.resource_ref.startswith('kms.'):
            return self.kms_template.stack
        elif ref.resource_ref == 'codecommit_role.arn':
            iam_ctl = self.aim_ctx.get_controller("IAM")
            return iam_ctl.role_arn(ref.raw[:-4])
        elif ref.resource_ref == 'codecommit.arn':
            codecommit_ref = ref.resource.codecommit_repository
            return self.aim_ctx.get_ref(codecommit_ref+".arn")
        elif ref.resource_ref == 'codebuild_role.arn':
            # self.cpbd_codepipebuild_template will fail if there are two deployments
            # this application... corner case, but might happen?
            return ref.resource._template.get_codebuild_role_arn()
        elif ref.resource_ref == 'codepipeline_role.arn':
            return ref.resource._template.get_codepipeline_role_arn()
        elif ref.resource_ref == 'codedeploy_tools_delegate_role.arn':
            return ref.resource._template.get_tools_delegate_role_arn()
        elif ref.resource_ref.startswith('kms.'):
            return self.kms_template.stack
        elif ref.resource_ref == 'codedeploy_application_name':
            return ref.resource._template.get_application_name()
        elif ref.resource_ref == 'deploy.deployment_group.name':
            return ref.resource._template.stack
        else:
            breakpoint()