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
  description = "SageMaker instance type for the full-precision BF16 model endpoint"
}
