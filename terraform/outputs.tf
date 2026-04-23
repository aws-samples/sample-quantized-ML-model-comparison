# Terraform outputs for endpoint names

output "quantized_endpoint_name" {
  description = "Name of the quantized SageMaker endpoint"
  value       = aws_sagemaker_endpoint.quantized.name
}

output "full_precision_endpoint_name" {
  description = "Name of the full-precision SageMaker endpoint"
  value       = aws_sagemaker_endpoint.full_precision.name
}

output "notebook_instance_url" {
  description = "URL of the SageMaker Notebook Instance (only available when create_notebook_instance = true)"
  value       = var.create_notebook_instance ? "https://${aws_sagemaker_notebook_instance.notebook[0].name}.notebook.${var.aws_region}.sagemaker.aws/tree" : null
}
