terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ---------------------------------------------------------------------------
# Data sources for constructing the ECR image URI
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  ecr_repo_name  = "qwen3-vl-llamacpp"
  # Use a content-based tag derived from the Dockerfile and entrypoint hashes
  # so each build gets a unique immutable tag instead of overwriting :latest
  ecr_image_tag  = substr(md5("${file("${path.module}/Dockerfile")}${file("${path.module}/serving_script/entrypoint.sh")}"), 0, 12)
  ecr_image_uri  = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.name}.amazonaws.com/${local.ecr_repo_name}:${local.ecr_image_tag}"
}

# ---------------------------------------------------------------------------
# ECR repository for the llama.cpp BYOC container
# ---------------------------------------------------------------------------

resource "aws_ecr_repository" "llamacpp" {
  name                 = local.ecr_repo_name
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
  }

  tags = {
    Project = "qwen3-vl-quantized-comparison"
  }
}

# ---------------------------------------------------------------------------
# KMS key for S3 bucket encryption
# ---------------------------------------------------------------------------

resource "aws_kms_key" "s3_codebuild" {
  description             = "CMK for CodeBuild source S3 bucket encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowKeyAdministration"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action = [
          "kms:Create*",
          "kms:Describe*",
          "kms:Enable*",
          "kms:List*",
          "kms:Put*",
          "kms:Update*",
          "kms:Revoke*",
          "kms:Disable*",
          "kms:Get*",
          "kms:Delete*",
          "kms:TagResource",
          "kms:UntagResource",
          "kms:ScheduleKeyDeletion",
          "kms:CancelKeyDeletion"
        ]
        Resource = "*"
      },
      {
        Sid    = "AllowS3Encryption"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.codebuild_role.arn
        }
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = "*"
      },
      {
        Sid    = "AllowCloudWatchLogs"
        Effect = "Allow"
        Principal = {
          Service = "logs.${var.aws_region}.amazonaws.com"
        }
        Action = [
          "kms:Encrypt*",
          "kms:Decrypt*",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:Describe*"
        ]
        Resource = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/codebuild/*"
          }
        }
      }
    ]
  })

  tags = {
    Project = "qwen3-vl-quantized-comparison"
  }
}

resource "aws_kms_alias" "s3_codebuild" {
  name          = "alias/qwen3-vl-codebuild-s3"
  target_key_id = aws_kms_key.s3_codebuild.key_id
}

# ---------------------------------------------------------------------------
# ECR repository policy — restrict to same-account principals
# ---------------------------------------------------------------------------

resource "aws_ecr_repository_policy" "llamacpp" {
  repository = aws_ecr_repository.llamacpp.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowSameAccountAccess"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload"
        ]
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# KMS key for SageMaker endpoint encryption at rest
# ---------------------------------------------------------------------------

resource "aws_kms_key" "sagemaker_endpoint" {
  description             = "CMK for SageMaker endpoint data encryption at rest"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowKeyAdministration"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action = [
          "kms:Create*",
          "kms:Describe*",
          "kms:Enable*",
          "kms:List*",
          "kms:Put*",
          "kms:Update*",
          "kms:Revoke*",
          "kms:Disable*",
          "kms:Get*",
          "kms:Delete*",
          "kms:TagResource",
          "kms:UntagResource",
          "kms:ScheduleKeyDeletion",
          "kms:CancelKeyDeletion"
        ]
        Resource = "*"
      },
      {
        Sid    = "AllowSageMakerEncryption"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.sagemaker_execution_role.arn
        }
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = "*"
      },
      {
        Sid    = "AllowCloudWatchLogs"
        Effect = "Allow"
        Principal = {
          Service = "logs.${var.aws_region}.amazonaws.com"
        }
        Action = [
          "kms:Encrypt*",
          "kms:Decrypt*",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:Describe*"
        ]
        Resource = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/sagemaker/*"
          }
        }
      }
    ]
  })

  tags = {
    Project = "qwen3-vl-quantized-comparison"
  }
}

resource "aws_kms_alias" "sagemaker_endpoint" {
  name          = "alias/qwen3-vl-sagemaker-endpoint"
  target_key_id = aws_kms_key.sagemaker_endpoint.key_id
}

# ---------------------------------------------------------------------------
# CloudWatch Log Groups with retention and encryption
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "codebuild" {
  name              = "/codebuild/qwen3-vl-llamacpp-build"
  retention_in_days = 365
  kms_key_id        = aws_kms_key.s3_codebuild.arn

  tags = {
    Project = "qwen3-vl-quantized-comparison"
  }
}

resource "aws_cloudwatch_log_group" "sagemaker_quantized" {
  name              = "/aws/sagemaker/Endpoints/qwen3-vl-8b-quantized"
  retention_in_days = 365
  kms_key_id        = aws_kms_key.sagemaker_endpoint.arn

  tags = {
    Project = "qwen3-vl-quantized-comparison"
  }
}

resource "aws_cloudwatch_log_group" "sagemaker_full_precision" {
  name              = "/aws/sagemaker/Endpoints/qwen3-vl-8b-full-precision"
  retention_in_days = 365
  kms_key_id        = aws_kms_key.sagemaker_endpoint.arn

  tags = {
    Project = "qwen3-vl-quantized-comparison"
  }
}

# ---------------------------------------------------------------------------
# S3 bucket for CodeBuild source
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "codebuild_source" {
  bucket_prefix = "qwen3-vl-build-"
  force_destroy = true

  tags = {
    Project = "qwen3-vl-quantized-comparison"
  }
}

resource "aws_s3_bucket_public_access_block" "codebuild_source" {
  bucket = aws_s3_bucket.codebuild_source.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "codebuild_source" {
  bucket = aws_s3_bucket.codebuild_source.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.s3_codebuild.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_versioning" "codebuild_source" {
  bucket = aws_s3_bucket.codebuild_source.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "codebuild_source" {
  bucket = aws_s3_bucket.codebuild_source.id

  rule {
    id     = "expire-old-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }

  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# ---------------------------------------------------------------------------
# Package build context and upload to S3
# ---------------------------------------------------------------------------

data "archive_file" "build_context" {
  type        = "zip"
  output_path = "${path.module}/.build-context.zip"

  source {
    content  = file("${path.module}/Dockerfile")
    filename = "Dockerfile"
  }

  source {
    content  = file("${path.module}/serving_script/entrypoint.sh")
    filename = "serving_script/entrypoint.sh"
  }
}

resource "aws_s3_object" "build_context" {
  bucket = aws_s3_bucket.codebuild_source.id
  key    = "build-context.zip"
  source = data.archive_file.build_context.output_path
  etag   = data.archive_file.build_context.output_md5
}

# ---------------------------------------------------------------------------
# IAM role for CodeBuild
# ---------------------------------------------------------------------------

resource "aws_iam_role" "codebuild_role" {
  name = "qwen3-vl-codebuild-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "codebuild.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Project = "qwen3-vl-quantized-comparison"
  }
}

resource "aws_iam_role_policy" "codebuild_permissions" {
  name = "qwen3-vl-codebuild-permissions"
  role = aws_iam_role.codebuild_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECRAuth"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken"
        ]
        Resource = "*"
        # Note: ecr:GetAuthorizationToken does not support resource-level permissions
        # and requires Resource = "*" per AWS documentation.
        # This returns a temporary Docker login token, not IAM credentials.
      },
      {
        Sid    = "ECRPush"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload"
        ]
        Resource = aws_ecr_repository.llamacpp.arn
      },
      {
        Sid    = "S3Source"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion"
        ]
        Resource = "${aws_s3_bucket.codebuild_source.arn}/*"
      },
      {
        Sid    = "KMSDecrypt"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = aws_kms_key.s3_codebuild.arn
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/codebuild/qwen3-vl-llamacpp-build:*"
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# CodeBuild project to build and push the Docker image
# ---------------------------------------------------------------------------

resource "aws_codebuild_project" "docker_build" {
  name           = "qwen3-vl-llamacpp-build"
  description    = "Build and push the llama.cpp BYOC container for quantized model serving"
  service_role   = aws_iam_role.codebuild_role.arn
  encryption_key = "alias/aws/s3"

  # Use a large compute type — the build downloads ~6.4 GB of model weights
  # and serves via Docker, so it needs substantial memory and disk
  environment {
    compute_type                = "BUILD_GENERAL1_LARGE"
    image                       = "aws/codebuild/standard:7.0"
    type                        = "LINUX_CONTAINER"
    privileged_mode             = true  # Required for Docker-in-Docker builds
    image_pull_credentials_type = "CODEBUILD"

    environment_variable {
      name  = "ECR_REPO_URI"
      value = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.name}.amazonaws.com/${local.ecr_repo_name}"
    }

    environment_variable {
      name  = "IMAGE_TAG"
      value = local.ecr_image_tag
    }

    environment_variable {
      name  = "AWS_DEFAULT_REGION"
      value = var.aws_region
    }

    environment_variable {
      name  = "AWS_ACCOUNT_ID"
      value = data.aws_caller_identity.current.account_id
    }
  }

  source {
    type     = "S3"
    location = "${aws_s3_bucket.codebuild_source.id}/build-context.zip"

    buildspec = <<-BUILDSPEC
      version: 0.2
      phases:
        pre_build:
          commands:
            - echo Logging in to Amazon ECR...
            - aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com
        build:
          commands:
            - echo Building Docker image with tag $IMAGE_TAG...
            - docker build -t $ECR_REPO_URI:$IMAGE_TAG .
        post_build:
          commands:
            - echo Pushing Docker image to ECR...
            - docker push $ECR_REPO_URI:$IMAGE_TAG
            - echo Build completed on $(date)
    BUILDSPEC
  }

  artifacts {
    type = "NO_ARTIFACTS"
  }

  logs_config {
    cloudwatch_logs {
      group_name  = "/codebuild/qwen3-vl-llamacpp-build"
      stream_name = "build-log"
    }
  }

  # 60-minute timeout — the build downloads large model files
  build_timeout = 60

  tags = {
    Project = "qwen3-vl-quantized-comparison"
  }
}

# ---------------------------------------------------------------------------
# Trigger CodeBuild and wait for completion
# ---------------------------------------------------------------------------

resource "null_resource" "codebuild_trigger" {
  depends_on = [
    aws_codebuild_project.docker_build,
    aws_s3_object.build_context,
    aws_ecr_repository.llamacpp,
    aws_iam_role_policy.codebuild_permissions,
    aws_cloudwatch_log_group.codebuild,
  ]

  triggers = {
    dockerfile_hash = filemd5("${path.module}/Dockerfile")
    entrypoint_hash = filemd5("${path.module}/serving_script/entrypoint.sh")
  }

  provisioner "local-exec" {
    command = <<-EOT
      echo "Starting CodeBuild project..."
      BUILD_ID=$(aws codebuild start-build \
        --project-name qwen3-vl-llamacpp-build \
        --region ${var.aws_region} \
        --query 'build.id' \
        --output text)

      echo "Build started: $BUILD_ID"
      echo "Waiting for build to complete (this may take 15-30 minutes)..."

      # Poll until build completes
      while true; do
        STATUS=$(aws codebuild batch-get-builds \
          --ids "$BUILD_ID" \
          --region ${var.aws_region} \
          --query 'builds[0].buildStatus' \
          --output text)

        if [ "$STATUS" = "SUCCEEDED" ]; then
          echo "Build succeeded!"
          break
        elif [ "$STATUS" = "FAILED" ] || [ "$STATUS" = "FAULT" ] || [ "$STATUS" = "STOPPED" ] || [ "$STATUS" = "TIMED_OUT" ]; then
          echo "Build failed with status: $STATUS"
          echo "Check CloudWatch logs at /codebuild/qwen3-vl-llamacpp-build for details."
          exit 1
        fi

        PHASE=$(aws codebuild batch-get-builds \
          --ids "$BUILD_ID" \
          --region ${var.aws_region} \
          --query 'builds[0].currentPhase' \
          --output text)
        echo "  Status: $STATUS | Phase: $PHASE"
        sleep 30
      done
    EOT
  }
}

# ---------------------------------------------------------------------------
# SageMaker Model — Quantized (BYOC llama.cpp with Q4_K_M GGUF)
# ---------------------------------------------------------------------------

resource "aws_sagemaker_model" "quantized" {
  name               = "qwen3-vl-8b-quantized"
  execution_role_arn = aws_iam_role.sagemaker_execution_role.arn

  primary_container {
    image = local.ecr_image_uri
  }

  depends_on = [null_resource.codebuild_trigger]

  tags = {
    Project      = "qwen3-vl-quantized-comparison"
    ModelVariant = "quantized-q4-k-m"
  }
}

# ---------------------------------------------------------------------------
# SageMaker Endpoint Configuration — Quantized
# ---------------------------------------------------------------------------

resource "aws_sagemaker_endpoint_configuration" "quantized" {
  name = "qwen3-vl-8b-quantized-config"

  kms_key_arn = aws_kms_key.sagemaker_endpoint.arn

  production_variants {
    variant_name           = "AllTraffic"
    model_name             = aws_sagemaker_model.quantized.name
    initial_instance_count = 1
    instance_type          = var.quantized_instance_type
  }

  tags = {
    Project      = "qwen3-vl-quantized-comparison"
    ModelVariant = "quantized-q4-k-m"
  }
}

# ---------------------------------------------------------------------------
# SageMaker Endpoint — Quantized
# ---------------------------------------------------------------------------

resource "aws_sagemaker_endpoint" "quantized" {
  name                 = "qwen3-vl-8b-quantized"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.quantized.name

  tags = {
    Project      = "qwen3-vl-quantized-comparison"
    ModelVariant = "quantized-q4-k-m"
  }
}

# ---------------------------------------------------------------------------
# SageMaker Model — Full-Precision (SageMaker LMI with vLLM, BF16)
# ---------------------------------------------------------------------------

resource "aws_sagemaker_model" "full_precision" {
  name               = "qwen3-vl-8b-full-precision"
  execution_role_arn = aws_iam_role.sagemaker_execution_role.arn

  primary_container {
    image = "763104351884.dkr.ecr.${var.aws_region}.amazonaws.com/djl-inference:0.35.0-lmi17.0.0-cu128"

    environment = {
      HF_MODEL_ID                   = "Qwen/Qwen3-VL-8B-Instruct"
      OPTION_DTYPE                  = "bf16"
      OPTION_ROLLING_BATCH          = "vllm"
      OPTION_TENSOR_PARALLEL_DEGREE = "4"
      OPTION_MAX_MODEL_LEN          = "4096"
      OPTION_GPU_MEMORY_UTILIZATION = "0.95"
      OPTION_ENFORCE_EAGER          = "true"
      OPTION_LIMIT_MM_PER_PROMPT    = "image=1"
    }
  }

  tags = {
    Project      = "qwen3-vl-quantized-comparison"
    ModelVariant = "full-precision-bf16"
  }
}

# ---------------------------------------------------------------------------
# SageMaker Endpoint Configuration — Full-Precision
# ---------------------------------------------------------------------------

resource "aws_sagemaker_endpoint_configuration" "full_precision" {
  name = "qwen3-vl-8b-full-precision-config"

  kms_key_arn = aws_kms_key.sagemaker_endpoint.arn

  production_variants {
    variant_name           = "AllTraffic"
    model_name             = aws_sagemaker_model.full_precision.name
    initial_instance_count = 1
    instance_type          = var.full_precision_instance_type
  }

  tags = {
    Project      = "qwen3-vl-quantized-comparison"
    ModelVariant = "full-precision-bf16"
  }
}

# ---------------------------------------------------------------------------
# SageMaker Endpoint — Full-Precision
# ---------------------------------------------------------------------------

resource "aws_sagemaker_endpoint" "full_precision" {
  name                 = "qwen3-vl-8b-full-precision"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.full_precision.name

  tags = {
    Project      = "qwen3-vl-quantized-comparison"
    ModelVariant = "full-precision-bf16"
  }
}
