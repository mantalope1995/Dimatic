import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as route53 from 'aws-cdk-lib/aws-route53';
import * as acm from 'aws-cdk-lib/aws-certificatemanager';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as elasticache from 'aws-cdk-lib/aws-elasticache';
import * as autoscaling from 'aws-cdk-lib/aws-applicationautoscaling';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as cloudwatch_actions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as wafv2 from 'aws-cdk-lib/aws-wafv2';
import * as servicediscovery from 'aws-cdk-lib/aws-servicediscovery';

export class DimaticInfraStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Create VPC with public and private subnets
    const vpc = new ec2.Vpc(this, 'DimaticVpc', {
      maxAzs: 2,
      natGateways: 1,
      ipAddresses: ec2.IpAddresses.cidr('10.0.0.0/16'),
      subnetConfiguration: [
        {
          cidrMask: 24,
          name: 'public',
          subnetType: ec2.SubnetType.PUBLIC,
        },
        {
          cidrMask: 24,
          name: 'private',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        },
      ],
    });

    // Create ECS Cluster with Fargate
    const cluster = new ecs.Cluster(this, 'DimaticCluster', {
      vpc: vpc,
      clusterName: 'dimatic-cluster',
      containerInsights: true,
    });

    // Create Secrets Manager for environment variables
    const supabaseUrlSecret = new secretsmanager.Secret(this, 'SupabaseUrlSecret', {
      secretName: 'dimatic/supabase-url',
      description: 'Supabase URL for the application',
    });

    const supabaseKeySecret = new secretsmanager.Secret(this, 'SupabaseKeySecret', {
      secretName: 'dimatic/supabase-key',
      description: 'Supabase API key for the application',
    });

    const redisUrlSecret = new secretsmanager.Secret(this, 'RedisUrlSecret', {
      secretName: 'dimatic/redis-url',
      description: 'Redis URL for the application',
    });

    // Create CloudWatch Log Group
    const logGroup = new logs.LogGroup(this, 'DimaticLogGroup', {
      logGroupName: '/ecs/dimatic-app',
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      retention: logs.RetentionDays.ONE_MONTH,
    });

    // Create Task Execution Role
    const taskExecutionRole = new iam.Role(this, 'DimaticTaskExecutionRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      description: 'Execution role for ECS tasks',
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonECSTaskExecutionRolePolicy'),
      ],
    });

    // Grant secrets access to task execution role
    supabaseUrlSecret.grantRead(taskExecutionRole);
    supabaseKeySecret.grantRead(taskExecutionRole);
    redisUrlSecret.grantRead(taskExecutionRole);

    // Create Application Load Balancer
    const alb = new elbv2.ApplicationLoadBalancer(this, 'DimaticALB', {
      vpc: vpc,
      internetFacing: true,
      loadBalancerName: 'dimatic-alb',
    });

    // Create ACM Certificate with DNS validation
    // Note: You'll need to create DNS records in your domain registrar
    const hostedZone = route53.HostedZone.fromLookup(this, 'HostedZone', {
      domainName: 'dimatic.com.au',
    });
    
    const certificate = new acm.Certificate(this, 'Certificate', {
      domainName: 'dimatic.com.au',
      subjectAlternativeNames: ['www.dimatic.com.au', 'api.dimatic.com.au'],
      validation: acm.CertificateValidation.fromDns(hostedZone),
    });

    // Create a listener for HTTPS
    const listener = alb.addListener('DimaticListener', {
      port: 443,
      certificates: [certificate],
    });

    // Create target groups for each service
    const frontendTargetGroup = new elbv2.ApplicationTargetGroup(this, 'FrontendTargetGroup', {
      vpc: vpc,
      port: 80,
      targetType: elbv2.TargetType.IP,
      healthCheck: {
        path: '/',
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
      },
    });

    const backendTargetGroup = new elbv2.ApplicationTargetGroup(this, 'BackendTargetGroup', {
      vpc: vpc,
      port: 8000,
      targetType: elbv2.TargetType.IP,
      healthCheck: {
        path: '/health',
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
      },
    });

    // Add default action to listener
    listener.addAction('DefaultAction', {
      action: elbv2.ListenerAction.fixedResponse(404, {
        contentType: 'text/plain',
        messageBody: 'Not Found',
      }),
    });

    // Add listener rules
    listener.addAction('FrontendRule', {
      priority: 1,
      conditions: [
        elbv2.ListenerCondition.hostHeaders(['dimatic.com.au', 'www.dimatic.com.au']),
      ],
      action: elbv2.ListenerAction.forward([frontendTargetGroup]),
    });

    listener.addAction('BackendRule', {
      priority: 2,
      conditions: [
        elbv2.ListenerCondition.hostHeaders(['api.dimatic.com.au']),
      ],
      action: elbv2.ListenerAction.forward([backendTargetGroup]),
    });

    // Create ECR repositories for container images
    const frontendRepository = new ecr.Repository(this, 'FrontendRepository', {
      repositoryName: 'dimatic-frontend',
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const backendRepository = new ecr.Repository(this, 'BackendRepository', {
      repositoryName: 'dimatic-backend',
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Create ElastiCache Redis cluster
    const redisSubnetGroup = new elasticache.CfnSubnetGroup(this, 'RedisSubnetGroup', {
      description: 'Subnet group for Redis cluster',
      subnetIds: vpc.privateSubnets.map(subnet => subnet.subnetId),
    });

    const redisSecurityGroup = new ec2.SecurityGroup(this, 'RedisSecurityGroup', {
      vpc: vpc,
      description: 'Security group for Redis cluster',
      allowAllOutbound: true,
    });

    // Allow ECS tasks to connect to Redis
    redisSecurityGroup.addIngressRule(
      ec2.Peer.ipv4(vpc.vpcCidrBlock),
      ec2.Port.tcp(6379),
      'Allow ECS tasks to connect to Redis'
    );

    const redisCluster = new elasticache.CfnReplicationGroup(this, 'RedisCluster', {
      replicationGroupDescription: 'Redis cluster for Dimatic application',
      replicationGroupId: 'dimatic-redis',
      cacheNodeType: 'cache.t3.micro',
      engine: 'redis',
      engineVersion: '7.x',
      numCacheClusters: 1,
      automaticFailoverEnabled: false,
      cacheSubnetGroupName: redisSubnetGroup.ref,
      securityGroupIds: [redisSecurityGroup.securityGroupId],
    });

    // Create security groups for services
    const frontendSecurityGroup = new ec2.SecurityGroup(this, 'FrontendSecurityGroup', {
      vpc: vpc,
      description: 'Security group for frontend service',
      allowAllOutbound: true,
    });

    const backendSecurityGroup = new ec2.SecurityGroup(this, 'BackendSecurityGroup', {
      vpc: vpc,
      description: 'Security group for backend service',
      allowAllOutbound: true,
    });

    const workerSecurityGroup = new ec2.SecurityGroup(this, 'WorkerSecurityGroup', {
      vpc: vpc,
      description: 'Security group for worker service',
      allowAllOutbound: true,
    });

    // Create Task Definitions
    // Frontend Task Definition
    const frontendTaskDefinition = new ecs.FargateTaskDefinition(this, 'FrontendTaskDefinition', {
      memoryLimitMiB: 512,
      cpu: 256,
      executionRole: taskExecutionRole,
    });

    frontendTaskDefinition.addContainer('FrontendContainer', {
      image: ecs.ContainerImage.fromEcrRepository(frontendRepository, 'latest'),
      portMappings: [{ containerPort: 3001 }],
      environment: {
        NEXT_PUBLIC_ENV_MODE: 'local',
        NEXT_PUBLIC_URL: 'https://dimatic.com.au',
        NEXT_PUBLIC_BACKEND_URL: 'https://api.dimatic.com.au',
      },
      secrets: {
        NEXT_PUBLIC_SUPABASE_URL: ecs.Secret.fromSecretsManager(supabaseUrlSecret),
        NEXT_PUBLIC_SUPABASE_ANON_KEY: ecs.Secret.fromSecretsManager(supabaseKeySecret),
      },
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: 'frontend', logGroup: logGroup }),
    });

    // Backend Task Definition
    const backendTaskDefinition = new ecs.FargateTaskDefinition(this, 'BackendTaskDefinition', {
      memoryLimitMiB: 1024,
      cpu: 512,
      executionRole: taskExecutionRole,
    });

    backendTaskDefinition.addContainer('BackendContainer', {
      image: ecs.ContainerImage.fromEcrRepository(backendRepository, 'latest'),
      portMappings: [{ containerPort: 8000 }],
      environment: {
        ENV_MODE: 'local',
        REDIS_HOST: redisCluster.attrPrimaryEndPointAddress,
        REDIS_PORT: '6379',
        REDIS_SSL: 'False',
      },
      secrets: {
        SUPABASE_URL: ecs.Secret.fromSecretsManager(supabaseUrlSecret),
        SUPABASE_ANON_KEY: ecs.Secret.fromSecretsManager(supabaseKeySecret),
        SUPABASE_SERVICE_ROLE_KEY: ecs.Secret.fromSecretsManager(supabaseKeySecret),
        REDIS_PASSWORD: ecs.Secret.fromSecretsManager(redisUrlSecret),
        // Add other secrets as needed
      },
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: 'backend', logGroup: logGroup }),
    });

    // Worker Task Definition
    const workerTaskDefinition = new ecs.FargateTaskDefinition(this, 'WorkerTaskDefinition', {
      memoryLimitMiB: 1024,
      cpu: 512,
      executionRole: taskExecutionRole,
    });

    workerTaskDefinition.addContainer('WorkerContainer', {
      image: ecs.ContainerImage.fromEcrRepository(backendRepository, 'latest'),
      command: ['uv', 'run', 'dramatiq', '--skip-logging', '--processes', '4', '--threads', '4', 'run_agent_background'],
      environment: {
        ENV_MODE: 'local',
        REDIS_HOST: redisCluster.attrPrimaryEndPointAddress,
        REDIS_PORT: '6379',
        REDIS_SSL: 'False',
      },
      secrets: {
        SUPABASE_URL: ecs.Secret.fromSecretsManager(supabaseUrlSecret),
        SUPABASE_ANON_KEY: ecs.Secret.fromSecretsManager(supabaseKeySecret),
        SUPABASE_SERVICE_ROLE_KEY: ecs.Secret.fromSecretsManager(supabaseKeySecret),
        REDIS_PASSWORD: ecs.Secret.fromSecretsManager(redisUrlSecret),
        // Add other secrets as needed
      },
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: 'worker', logGroup: logGroup }),
    });

    // Create ECS Services
    const frontendService = new ecs.FargateService(this, 'FrontendService', {
      cluster,
      taskDefinition: frontendTaskDefinition,
      desiredCount: 1,
      assignPublicIp: false,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      securityGroups: [frontendSecurityGroup],
    });

    const backendService = new ecs.FargateService(this, 'BackendService', {
      cluster,
      taskDefinition: backendTaskDefinition,
      desiredCount: 1,
      assignPublicIp: false,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      securityGroups: [backendSecurityGroup],
    });

    const workerService = new ecs.FargateService(this, 'WorkerService', {
      cluster,
      taskDefinition: workerTaskDefinition,
      desiredCount: 1,
      assignPublicIp: false,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      securityGroups: [workerSecurityGroup],
    });

    // Connect services to load balancer
    frontendTargetGroup.addTarget(frontendService);
    backendTargetGroup.addTarget(backendService);

    // === AUTO SCALING CONFIGURATION ===
    
    // Enable auto-scaling for Frontend Service
    const frontendScaling = frontendService.autoScaleTaskCount({
      minCapacity: 1,
      maxCapacity: 10,
    });

    // Add CPU-based scaling for Frontend
    frontendScaling.scaleOnCpuUtilization('CpuScaling', {
      targetUtilizationPercent: 70,
      scaleInCooldown: cdk.Duration.seconds(300),
      scaleOutCooldown: cdk.Duration.seconds(60),
    });

    // Add memory-based scaling for Frontend
    frontendScaling.scaleOnMemoryUtilization('MemoryScaling', {
      targetUtilizationPercent: 80,
      scaleInCooldown: cdk.Duration.seconds(300),
      scaleOutCooldown: cdk.Duration.seconds(60),
    });

    // Enable auto-scaling for Backend Service
    const backendScaling = backendService.autoScaleTaskCount({
      minCapacity: 1,
      maxCapacity: 10,
    });

    // Add CPU-based scaling for Backend
    backendScaling.scaleOnCpuUtilization('CpuScaling', {
      targetUtilizationPercent: 70,
      scaleInCooldown: cdk.Duration.seconds(300),
      scaleOutCooldown: cdk.Duration.seconds(60),
    });

    // Add memory-based scaling for Backend
    backendScaling.scaleOnMemoryUtilization('MemoryScaling', {
      targetUtilizationPercent: 80,
      scaleInCooldown: cdk.Duration.seconds(300),
      scaleOutCooldown: cdk.Duration.seconds(60),
    });

    // Add request-based scaling for Backend (based on ALB request count)
    backendScaling.scaleOnRequestCount('RequestScaling', {
      requestsPerTarget: 100,
      scaleInCooldown: cdk.Duration.seconds(300),
      scaleOutCooldown: cdk.Duration.seconds(60),
      targetGroup: backendTargetGroup,
    });

    // Enable auto-scaling for Worker Service
    const workerScaling = workerService.autoScaleTaskCount({
      minCapacity: 1,
      maxCapacity: 5,
    });

    // Add CPU-based scaling for Worker
    workerScaling.scaleOnCpuUtilization('CpuScaling', {
      targetUtilizationPercent: 70,
      scaleInCooldown: cdk.Duration.seconds(300),
      scaleOutCooldown: cdk.Duration.seconds(60),
    });

    // Add memory-based scaling for Worker
    workerScaling.scaleOnMemoryUtilization('MemoryScaling', {
      targetUtilizationPercent: 80,
      scaleInCooldown: cdk.Duration.seconds(300),
      scaleOutCooldown: cdk.Duration.seconds(60),
    });

    // === CLOUDWATCH MONITORING AND ALARMS ===

    // Create CloudWatch Alarms for Frontend Service
    const frontendCpuAlarm = new cloudwatch.Alarm(this, 'FrontendCpuAlarm', {
      alarmName: 'Dimatic-Frontend-High-CPU',
      alarmDescription: 'Frontend service CPU utilization is too high',
      metric: frontendService.metricCpuUtilization({
        period: cdk.Duration.minutes(5),
        statistic: cloudwatch.Statistic.AVERAGE,
      }),
      threshold: 80,
      evaluationPeriods: 2,
      datapointsToAlarm: 2,
    });

    const frontendMemoryAlarm = new cloudwatch.Alarm(this, 'FrontendMemoryAlarm', {
      alarmName: 'Dimatic-Frontend-High-Memory',
      alarmDescription: 'Frontend service memory utilization is too high',
      metric: frontendService.metricMemoryUtilization({
        period: cdk.Duration.minutes(5),
        statistic: cloudwatch.Statistic.AVERAGE,
      }),
      threshold: 90,
      evaluationPeriods: 2,
      datapointsToAlarm: 2,
    });

    // Create CloudWatch Alarms for Backend Service
    const backendCpuAlarm = new cloudwatch.Alarm(this, 'BackendCpuAlarm', {
      alarmName: 'Dimatic-Backend-High-CPU',
      alarmDescription: 'Backend service CPU utilization is too high',
      metric: backendService.metricCpuUtilization({
        period: cdk.Duration.minutes(5),
        statistic: cloudwatch.Statistic.AVERAGE,
      }),
      threshold: 80,
      evaluationPeriods: 2,
      datapointsToAlarm: 2,
    });

    const backendMemoryAlarm = new cloudwatch.Alarm(this, 'BackendMemoryAlarm', {
      alarmName: 'Dimatic-Backend-High-Memory',
      alarmDescription: 'Backend service memory utilization is too high',
      metric: backendService.metricMemoryUtilization({
        period: cdk.Duration.minutes(5),
        statistic: cloudwatch.Statistic.AVERAGE,
      }),
      threshold: 90,
      evaluationPeriods: 2,
      datapointsToAlarm: 2,
    });

    // Create ALB Target Health Alarms
    const frontendTargetHealthAlarm = new cloudwatch.Alarm(this, 'FrontendTargetHealthAlarm', {
      alarmName: 'Dimatic-Frontend-Unhealthy-Hosts',
      alarmDescription: 'Frontend target has unhealthy hosts',
      metric: frontendTargetGroup.metricUnhealthyHostCount({
        period: cdk.Duration.minutes(1),
        statistic: cloudwatch.Statistic.SUM,
      }),
      threshold: 1,
      evaluationPeriods: 2,
      datapointsToAlarm: 2,
    });

    const backendTargetHealthAlarm = new cloudwatch.Alarm(this, 'BackendTargetHealthAlarm', {
      alarmName: 'Dimatic-Backend-Unhealthy-Hosts',
      alarmDescription: 'Backend target has unhealthy hosts',
      metric: backendTargetGroup.metricUnhealthyHostCount({
        period: cdk.Duration.minutes(1),
        statistic: cloudwatch.Statistic.SUM,
      }),
      threshold: 1,
      evaluationPeriods: 2,
      datapointsToAlarm: 2,
    });

    // Create ALB Request Count Alarm (high traffic)
    const albRequestCountAlarm = new cloudwatch.Alarm(this, 'ALBRequestCountAlarm', {
      alarmName: 'Dimatic-ALB-High-Requests',
      alarmDescription: 'ALB is receiving high request count',
      metric: alb.metricRequestCount({
        period: cdk.Duration.minutes(5),
        statistic: cloudwatch.Statistic.SUM,
      }),
      threshold: 1000,
      evaluationPeriods: 2,
      datapointsToAlarm: 2,
    });

    // Create CloudWatch Dashboard for monitoring
    const dashboard = new cloudwatch.Dashboard(this, 'DimaticDashboard', {
      dashboardName: 'Dimatic-Infrastructure',
    });

    // Add widgets to dashboard
    dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'Frontend Service - CPU Utilization',
        left: [frontendService.metricCpuUtilization()],
        width: 12,
        height: 6,
      })
    );

    dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'Backend Service - CPU Utilization',
        left: [backendService.metricCpuUtilization()],
        width: 12,
        height: 6,
      })
    );

    dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'ALB Request Count',
        left: [alb.metricRequestCount()],
        width: 24,
        height: 6,
      })
    );

    dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'Target Group Health',
        left: [
          frontendTargetGroup.metricHealthyHostCount(),
          backendTargetGroup.metricHealthyHostCount(),
        ],
        width: 24,
        height: 6,
      })
    );

    // Output the VPC ID, Cluster Name, ALB DNS, and Redis endpoint
    new cdk.CfnOutput(this, 'VpcId', {
      value: vpc.vpcId,
      description: 'ID of the created VPC',
    });

    new cdk.CfnOutput(this, 'ClusterName', {
      value: cluster.clusterName,
      description: 'Name of the ECS Cluster',
    });

    new cdk.CfnOutput(this, 'ALBDnsName', {
      value: alb.loadBalancerDnsName,
      description: 'DNS name of the Application Load Balancer',
    });

    new cdk.CfnOutput(this, 'RedisEndpoint', {
      value: redisCluster.attrPrimaryEndPointAddress,
      description: 'Redis cluster endpoint address',
    });

    new cdk.CfnOutput(this, 'FrontendRepositoryUri', {
      value: frontendRepository.repositoryUri,
      description: 'URI of the frontend ECR repository',
    });

    new cdk.CfnOutput(this, 'BackendRepositoryUri', {
      value: backendRepository.repositoryUri,
      description: 'URI of the backend ECR repository',
    });
  }
}
