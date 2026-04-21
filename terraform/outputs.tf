# Terraform outputs for endpoint names

output "quantized_endpoint_name" {
  description = "Name of the quantized SageMaker endpoint"
  value       = aws_sagemaker_endpoint.quantized.name
}

output "full_precision_endpoint_name" {
  description = "Name of the full-precision SageMaker endpoint"
  value       = aws_sagemaker_endpoint.full_precision.name
}
