from paco.cftemplates.cftemplates import StackTemplate
import troposphere
import troposphere.route53


class Route53HostedZone(StackTemplate):
    def __init__(self, stack, paco_ctx):
        zone_config = stack.resource
        config_ref = zone_config.paco_ref_parts
        super().__init__(stack, paco_ctx, iam_capabilities=["CAPABILITY_NAMED_IAM"])
        self.set_aws_name('HostedZone', zone_config.name)
        self.init_template('Route53 Hosted Zone: ' + zone_config.domain_name)

        self.paco_ctx.log_action_col("Init", "Route53", "Hosted Zone", "{}".format(zone_config.domain_name))

        if zone_config.external_resource != None and zone_config.external_resource.is_enabled():
            hosted_zone_id_output_value = zone_config.external_resource.hosted_zone_id
            nameservers_output_value = ','.join(zone_config.external_resource.nameservers)
        else:
            hosted_zone_res = troposphere.route53.HostedZone(
                title='HostedZone',
                template=self.template,
                Name=zone_config.domain_name
            )
            hosted_zone_id_output_value = troposphere.Ref(hosted_zone_res)
            nameservers_output_value = troposphere.Join(',', troposphere.GetAtt(hosted_zone_res, 'NameServers'))

        self.create_output(
            title='HostedZoneId',
            value=hosted_zone_id_output_value,
            ref=config_ref+'.id'
        )
        self.create_output(
            title='HostedZoneNameServers',
            value=nameservers_output_value,
            ref=config_ref+'.name_servers'
        )

        if len(zone_config.record_sets) > 0:
            record_set_list = []
            for record_set_config in zone_config.record_sets:
                record_set_res = troposphere.route53.RecordSet(
                    Name=record_set_config.record_name,
                    Type=record_set_config.type,
                    TTL=record_set_config.ttl,
                    ResourceRecords=record_set_config.resource_records
                )
                record_set_list.append(record_set_res)

            group_res = troposphere.route53.RecordSetGroup(
                title='RecordSetGroup',
                template=self.template,
                HostedZoneId=troposphere.Ref(hosted_zone_res),
                RecordSets=record_set_list
            )
            group_res.DependsOn = hosted_zone_res
