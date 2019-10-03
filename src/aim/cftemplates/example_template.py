import os
import troposphere
#import troposphere.<resource>

from aim.cftemplates.cftemplates import CFTemplate


class Example(CFTemplate):
    def __init__(
        self,
        aim_ctx,
        account_ctx,
        aws_region,
        stack_group,
        stack_tags,

        grp_id,
        res_id,
        example_config,
        config_ref):

        # ---------------------------------------------------------------------------
        # CFTemplate Initialization
        super().__init__(
            aim_ctx,
            account_ctx,
            aws_region,
            enabled=example_config.is_enabled(),
            config_ref=config_ref,
            stack_group=stack_group,
            stack_tags=stack_tags,
            change_protected=example_config.change_protected
        )
        self.set_aws_name('Example', grp_id, res_id)

        # ---------------------------------------------------------------------------
        # Troposphere Template Initialization

        template = troposphere.Template(
            Description = 'Example Template',
        )
        template.set_version()
        template.add_resource(
            troposphere.cloudformation.WaitConditionHandle(title="EmptyTemplatePlaceholder")
        )

        # ---------------------------------------------------------------------------
        # Parameters

        example_param = self.create_cfn_parameter(
            name='ExampleParameterName',
            param_type='String',
            description='Example parameter.',
            value=example_config.example_variable,
            use_troposphere=True,
            troposphere_template=template,
        )

        # ---------------------------------------------------------------------------
        # Resource
        example_dict = {
            'some_property' : troposphere.Ref(example_param)
        }
        example_res = troposphere.resource.Example.from_dict(
            'ExampleResource',
            example_dict
        )
        template.add_resource( example_res )

        # ---------------------------------------------------------------------------
        # Outputs
        example_output = troposphere.Output(
            title='ExampleResourceId',
            Description="Example resource Id.",
            Value=troposphere.Ref(example_res)
        )
        template.add_output(example_output)

        # AIM Stack Output Registration
        self.register_stack_output_config(config_ref + ".id", example_output.title)

        # Generate the Template
        self.set_template(template.to_yaml())

