# ---------------------------------------------------------------------------
# S3 bucket for CodeBuild source (stores the Dockerfile + entrypoint zip)
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
