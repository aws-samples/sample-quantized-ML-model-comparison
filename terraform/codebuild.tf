# ---------------------------------------------------------------------------
# CloudWatch Log Group for CodeBuild
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "codebuild" {
  name              = "/codebuild/qwen3-vl-llamacpp-build"
  retention_in_days = 365
  kms_key_id        = aws_kms_key.s3_codebuild.arn

  tags = {
    Project = "qwen3-vl-quantized-comparison"
  }
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
    aws_cloudwatch_log_group.codebuild,
    time_sleep.wait_for_iam,
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
