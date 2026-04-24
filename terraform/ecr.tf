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

# Restrict ECR access to same-account principals only
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
