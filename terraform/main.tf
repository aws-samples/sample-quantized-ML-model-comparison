# ---------------------------------------------------------------------------
# Terraform configuration and provider
# ---------------------------------------------------------------------------

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
    time = {
      source  = "hashicorp/time"
      version = "~> 0.9"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ---------------------------------------------------------------------------
# Data sources and locals
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  ecr_repo_name = "qwen3-vl-llamacpp"
  # Use a content-based tag derived from the Dockerfile and entrypoint hashes
  # so each build gets a unique immutable tag instead of overwriting :latest
  ecr_image_tag = substr(md5("${file("${path.module}/Dockerfile")}${file("${path.module}/serving_script/entrypoint.sh")}"), 0, 12)
  ecr_image_uri = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.name}.amazonaws.com/${local.ecr_repo_name}:${local.ecr_image_tag}"
}

# ---------------------------------------------------------------------------
# IAM eventual consistency delay
# ---------------------------------------------------------------------------
# IAM policies can take up to 30 seconds to propagate after creation.
# Without this delay, CodeBuild and SageMaker may fail with ACCESS_DENIED.
# ---------------------------------------------------------------------------

resource "time_sleep" "wait_for_iam" {
  depends_on = [
    aws_iam_role_policy.codebuild_permissions,
    aws_iam_role_policy.sagemaker_custom_permissions,
    aws_iam_role_policy_attachment.sagemaker_full_access,
  ]

  create_duration = "30s"
}
