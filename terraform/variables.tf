variable "aws_region" {
  type        = string
  default     = "us-east-2"
  description = "AWS region to deploy SageMaker endpoints and supporting resources"
}

variable "quantized_instance_type" {
  type        = string
  default     = "ml.g5.xlarge"
  description = "SageMaker instance type for the quantized GGUF model endpoint"
}

variable "full_precision_instance_type" {
  type        = string
  default     = "ml.g5.12xlarge"
  description = "SageMaker instance type for the full-precision BF16 model endpoint (ml.g5.12xlarge provides 4x A10G GPUs for tensor parallelism)"
}

variable "create_notebook_instance" {
  type        = bool
  default     = true
  description = "Whether to provision a SageMaker Notebook Instance with the repository pre-cloned. Set to false to skip if you already have a Jupyter environment."
}

variable "notebook_instance_type" {
  type        = string
  default     = "ml.t3.medium"
  description = "SageMaker Notebook Instance type. ml.t3.medium is sufficient for running the comparison notebook (inference runs on the endpoints, not the notebook instance)."
}
