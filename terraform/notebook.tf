# ---------------------------------------------------------------------------
# Optional SageMaker Notebook Instance
# ---------------------------------------------------------------------------
# Provisions a Jupyter environment with the repository pre-cloned and
# dependencies installed. Gated behind var.create_notebook_instance
# (default true) so users get a ready-to-use environment out of the box.
# Set to false if you already have a Jupyter environment.
# ---------------------------------------------------------------------------

resource "aws_sagemaker_notebook_instance_lifecycle_configuration" "setup" {
  count = var.create_notebook_instance ? 1 : 0
  name  = "qwen3-vl-notebook-setup"

  on_create = base64encode(<<-EOF
    #!/bin/bash
    set -e
    # Install Python dependencies in the background to avoid the 5-minute
    # lifecycle config timeout. The nohup process continues after the
    # lifecycle script exits. A marker file signals completion.
    nohup sudo -u ec2-user -i <<'INNEREOF' &
    source activate base
    pip install --quiet -r /home/ec2-user/SageMaker/sample-quantized-ML-model-comparison/requirements.txt
    touch /home/ec2-user/SageMaker/.deps-installed
    INNEREOF
  EOF
  )
}

resource "aws_sagemaker_notebook_instance" "notebook" {
  count                   = var.create_notebook_instance ? 1 : 0
  name                    = "qwen3-vl-comparison-notebook"
  instance_type           = var.notebook_instance_type
  role_arn                = aws_iam_role.sagemaker_execution_role.arn
  default_code_repository = "https://github.com/aws-samples/sample-quantized-ML-model-comparison.git"
  lifecycle_config_name   = aws_sagemaker_notebook_instance_lifecycle_configuration.setup[0].name
  kms_key_id              = aws_kms_key.sagemaker_endpoint.arn
  root_access             = "Disabled"

  # VPC placement is not configured for this sample project. The notebook
  # only needs outbound internet access to invoke SageMaker endpoints and
  # clone the public GitHub repo. For production use, deploy in a VPC with
  # VPC endpoints for SageMaker, ECR, and S3.

  depends_on = [time_sleep.wait_for_iam]

  tags = {
    Project = "qwen3-vl-quantized-comparison"
  }
}
