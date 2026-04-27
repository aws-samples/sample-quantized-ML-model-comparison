# ---------------------------------------------------------------------------
# CloudWatch Log Groups for SageMaker endpoints
# ---------------------------------------------------------------------------

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
# SageMaker Model — Quantized (BYOC llama.cpp with UD-Q4_K_XL GGUF)
# ---------------------------------------------------------------------------

resource "aws_sagemaker_model" "quantized" {
  name               = "qwen3-vl-8b-quantized"
  execution_role_arn = aws_iam_role.sagemaker_execution_role.arn

  depends_on = [null_resource.codebuild_trigger, time_sleep.wait_for_iam]

  primary_container {
    image = local.ecr_image_uri
  }

  tags = {
    Project      = "qwen3-vl-quantized-comparison"
    ModelVariant = "quantized-ud-q4-k-xl"
  }
}

# ---------------------------------------------------------------------------
# SageMaker Endpoint Configuration — Quantized
# ---------------------------------------------------------------------------

resource "aws_sagemaker_endpoint_configuration" "quantized" {
  name = "qwen3-vl-8b-quantized-config"

  # NVMe instance storage is hardware-encrypted; KMS volume encryption not applicable

  production_variants {
    variant_name           = "AllTraffic"
    model_name             = aws_sagemaker_model.quantized.name
    initial_instance_count = 1
    instance_type          = var.quantized_instance_type
  }

  tags = {
    Project      = "qwen3-vl-quantized-comparison"
    ModelVariant = "quantized-ud-q4-k-xl"
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
    ModelVariant = "quantized-ud-q4-k-xl"
  }
}

# ---------------------------------------------------------------------------
# SageMaker Model — Full-Precision (SageMaker LMI with vLLM, BF16)
# ---------------------------------------------------------------------------

resource "aws_sagemaker_model" "full_precision" {
  name               = "qwen3-vl-8b-full-precision"
  execution_role_arn = aws_iam_role.sagemaker_execution_role.arn

  depends_on = [time_sleep.wait_for_iam]

  primary_container {
    image = "763104351884.dkr.ecr.${var.aws_region}.amazonaws.com/djl-inference:0.35.0-lmi17.0.0-cu128"

    environment = {
      HF_MODEL_ID                   = "Qwen/Qwen3-VL-8B-Instruct"
      OPTION_DTYPE                  = "bf16"
      OPTION_ROLLING_BATCH          = "vllm"
      OPTION_TENSOR_PARALLEL_DEGREE = "4"
      OPTION_MAX_MODEL_LEN          = "4096"
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

  # NVMe instance storage is hardware-encrypted; KMS volume encryption not applicable

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
