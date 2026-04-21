# IAM execution role for SageMaker model hosting

resource "aws_iam_role" "sagemaker_execution_role" {
  name = "sagemaker-qwen3-vl-comparison-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "sagemaker.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Project = "qwen3-vl-quantized-comparison"
  }
}

# Attach AmazonSageMakerFullAccess managed policy for SageMaker hosting permissions
# NOTE: This broad policy is used for simplicity in this demo. For production
# deployments, create a custom policy with only the specific permissions needed
# for model hosting (e.g., sagemaker:InvokeEndpoint, sagemaker:CreateModel, etc.)
resource "aws_iam_role_policy_attachment" "sagemaker_full_access" {
  role       = aws_iam_role.sagemaker_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSageMakerFullAccess"
}

# Custom inline policy for ECR pull access, S3 model artifacts, and CloudWatch Logs
resource "aws_iam_role_policy" "sagemaker_custom_permissions" {
  name = "sagemaker-qwen3-vl-custom-permissions"
  role = aws_iam_role.sagemaker_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECRPullAccess"
        Effect = "Allow"
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability"
        ]
        Resource = "*"
      },
      {
        Sid    = "S3ModelArtifactAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchLogging"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}
