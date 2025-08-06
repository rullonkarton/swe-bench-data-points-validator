#!/usr/bin/env python3
"""
Data quality checker for SWE-bench test cases
Automatic validation of data points and conversion to prediction format
"""

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

# Logging configuration for process tracking
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s | %(levelname)s | %(message)s'
)
log_instance = logging.getLogger(__name__)


class DataSetLoader:
    """Dataset loader from JSON format"""
    
    def __init__(self):
        """Initialize the loader"""
        self.processed_count = 0
    
    def load_datasets(self, source_folder: Path, file_list: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Loads datasets from specified folder
        
        Args:
            source_folder: Folder with JSON data files
            file_list: Optional list of file names to load
            
        Returns:
            List of dictionaries with data
        """
        log_instance.info(f"Starting load from folder: {source_folder}")
        
        if not source_folder.exists():
            log_instance.error(f"Source folder not found: {source_folder}")
            return []
        
        dataset_collection = []
        
        if file_list is None:
            # Load all JSON files
            json_file_paths = list(source_folder.glob("*.json"))
        else:
            # Load only specified files
            json_file_paths = []
            for filename in file_list:
                if not filename.endswith('.json'):
                    filename = filename + '.json'
                
                full_path = source_folder / filename
                if full_path.exists():
                    json_file_paths.append(full_path)
                else:
                    log_instance.warning(f"File not found: {filename}")
        
        log_instance.info(f"Found {len(json_file_paths)} JSON files for processing")
        
        if not json_file_paths:
            log_instance.warning("No JSON files found for loading")
            return []
        
        for json_path in json_file_paths:
            log_instance.info(f"Processing file: {json_path.name}")
            dataset_item = self._parse_json_file(json_path)
            
            if dataset_item:
                item_id = dataset_item.get("instance_id", "unknown")
                log_instance.info(f"Loaded item: {item_id}")
                dataset_collection.append(dataset_item)
                self.processed_count += 1
            else:
                log_instance.warning(f"Failed to load: {json_path.name}")
        
        log_instance.info(f"Total loaded items: {len(dataset_collection)}")
        return dataset_collection
    
    def _parse_json_file(self, json_path: Path) -> Optional[Dict[str, Any]]:
        """
        Parses a single JSON file
        
        Args:
            json_path: Path to JSON file
            
        Returns:
            Dictionary with data or None on error
        """
        try:
            with open(json_path, 'r', encoding='utf-8') as file_handle:
                dataset_content = json.load(file_handle)
            
            if self._check_data_integrity(dataset_content):
                return dataset_content
            else:
                log_instance.warning(f"Data integrity check failed: {json_path.name}")
                return None
                
        except json.JSONDecodeError as json_err:
            log_instance.error(f"JSON parsing error in {json_path.name}: {json_err}")
            return None
        except Exception as general_err:
            log_instance.error(f"General error loading {json_path.name}: {general_err}")
            return None
    
    def _check_data_integrity(self, dataset_item: Dict[str, Any]) -> bool:
        """
        Checks data structure integrity
        
        Args:
            dataset_item: Data item to check
            
        Returns:
            True if structure is correct, False otherwise
        """
        mandatory_fields = [
            "instance_id",
            "repo", 
            "base_commit",
            "patch",
            "FAIL_TO_PASS",
            "PASS_TO_PASS"
        ]
        
        for field_name in mandatory_fields:
            if field_name not in dataset_item:
                log_instance.warning(f"Missing required field '{field_name}'")
                return False
        
        patch_content = dataset_item.get("patch", "")
        if not patch_content.strip():
            log_instance.warning("Patch field is empty")
            return False
        
        failing_tests = dataset_item.get("FAIL_TO_PASS", [])
        passing_tests = dataset_item.get("PASS_TO_PASS", [])
        
        if not failing_tests and not passing_tests:
            log_instance.warning("Missing test cases FAIL_TO_PASS and PASS_TO_PASS")
            return False
        
        return True


class PredictionFormatter:
    """Formatter for converting to SWE-bench prediction format"""
    
    def __init__(self, ai_model: str = "gpt-4"):
        self.ai_model_name = ai_model
        self.conversion_stats = {"success": 0, "failed": 0}
    
    def transform_to_predictions(self, dataset_items: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Converts data items to prediction format"""
        log_instance.info(f"Starting conversion of {len(dataset_items)} items to prediction format")
        
        prediction_list = []
        
        for dataset_item in dataset_items:
            converted_prediction = self._transform_single_item(dataset_item)
            
            if converted_prediction:
                prediction_list.append(converted_prediction)
                self.conversion_stats["success"] += 1
            else:
                self.conversion_stats["failed"] += 1
                log_instance.warning(f"Failed to convert item: {dataset_item.get('instance_id', 'unknown')}")
        
        log_instance.info(f"Conversion completed: {self.conversion_stats['success']} successful, {self.conversion_stats['failed']} failed")
        return prediction_list
    
    def _transform_single_item(self, dataset_item: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Converts a single data item"""
        item_id = dataset_item.get("instance_id")
        patch_data = dataset_item.get("patch")
        
        if not item_id or not patch_data:
            log_instance.warning(f"Missing required fields: instance_id={item_id}, patch={'present' if patch_data else 'missing'}")
            return None
        
        formatted_prediction = {
            "instance_id": item_id,
            "model_name_or_path": self.ai_model_name,
            "model_patch": patch_data
        }
        
        return formatted_prediction
    
    def write_predictions_file(self, prediction_data: List[Dict[str, str]], output_path: str) -> bool:
        """Writes predictions to file"""
        log_instance.info(f"Saving {len(prediction_data)} predictions to file: {output_path}")
        
        try:
            with open(output_path, 'w', encoding='utf-8') as output_file:
                for prediction_entry in prediction_data:
                    output_file.write(json.dumps(prediction_entry) + '\n')
            
            log_instance.info(f"Predictions successfully saved: {output_path}")
            return True
            
        except Exception as write_error:
            log_instance.error(f"File write error {output_path}: {write_error}")
            return False


class DataPointProcessor:
    """Main processor for data point validation"""
    
    def __init__(self, data_folder: str = "data_points"):
        self.source_directory = Path(data_folder)
        self.dataset_loader = DataSetLoader()
        self.prediction_formatter = PredictionFormatter(ai_model="gpt-4")
        self.validation_metrics = {}
    
    def process_validation(self, target_files: Optional[List[str]] = None) -> Dict[str, Any]:
        """Runs validation process for specified or all files"""
        try:
            if target_files is None:
                # Process all JSON files
                json_files_found = list(self.source_directory.glob("*.json"))
                target_files = [f.stem for f in json_files_found]
                log_instance.info(f"Processing {len(target_files)} files")
            else:
                log_instance.info(f"Processing {len(target_files)} specified files")
            
            if not target_files:
                return {"error": "No files found for processing"}
            
            processing_summary = {
                "total_processed": len(target_files),
                "success_count": 0,
                "error_count": 0,
                "individual_results": {}
            }
            
            for filename in target_files:
                log_instance.info(f"Processing: {filename}")
                file_validation_result = self._process_single_file(filename)
                processing_summary["individual_results"][filename] = file_validation_result
                
                if file_validation_result.get("success", False):
                    processing_summary["success_count"] += 1
                else:
                    processing_summary["error_count"] += 1
                    log_instance.error(f"File error: {filename} - {file_validation_result.get('error', 'unknown error')}")
            
            success_percentage = (processing_summary["success_count"] / processing_summary["total_processed"]) * 100 if processing_summary["total_processed"] > 0 else 0
            processing_summary["success_percentage"] = success_percentage
            
            return processing_summary
            
        except Exception as processing_error:
            log_instance.error(f"Validation error: {processing_error}")
            return {"error": str(processing_error)}
    
    def _process_single_file(self, filename: str) -> Dict[str, Any]:
        """Processes a single file"""
        execution_id = filename
        predictions_output_file = f"predictions_{filename}.jsonl"
        logs_directory = Path("logs/run_evaluation") / execution_id / "gpt-4"
        
        try:
            # Load data
            loaded_datasets = self.dataset_loader.load_datasets(self.source_directory, [filename])
            
            if not loaded_datasets:
                return {"success": False, "error": f"Failed to load {filename}.json"}
            
            dataset_entry = loaded_datasets[0]
            entry_instance_id = dataset_entry.get("instance_id", "unknown")
            
            # Convert to prediction format
            formatted_predictions = self.prediction_formatter.transform_to_predictions([dataset_entry])
            
            if not formatted_predictions:
                return {"success": False, "error": "Failed to convert to prediction format"}
            
            # Save predictions file
            if not self.prediction_formatter.write_predictions_file(formatted_predictions, predictions_output_file):
                return {"success": False, "error": "Failed to save predictions file"}
            
            # Run Docker evaluation
            docker_execution_result = self._run_docker_evaluation(predictions_output_file, execution_id)
            
            if not docker_execution_result["success"]:
                return {"success": False, "error": f"Docker evaluation failed: {docker_execution_result['error']}"}
            
            # Check results
            result_analysis = self._analyze_test_results(dataset_entry, logs_directory)
            
            return {
                "success": True,
                "instance_id": entry_instance_id,
                "run_id": execution_id,
                "validation_analysis": result_analysis
            }
            
        except Exception as file_error:
            log_instance.error(f"Error processing {filename}: {file_error}")
            return {"success": False, "error": str(file_error)}
    
    def _run_docker_evaluation(self, predictions_file: str, execution_id: str) -> Dict[str, Any]:
        """Runs Docker container for evaluation"""
        docker_command = [
            "docker", "compose", "run", "--rm", "data-quality-checker",
            "python", "-m", "swebench.harness.run_evaluation",
            "--predictions_path", predictions_file,
            "--run_id", execution_id,
            "--dataset_name", "SWE-bench/SWE-bench",
            "--clean", "True"
        ]
        
        try:
            execution_result = subprocess.run(
                docker_command,
                capture_output=True,
                text=True,
                timeout=1800  # 30 minutes timeout
            )
            
            if execution_result.returncode == 0:
                return {"success": True}
            else:
                return {"success": False, "error": f"Exit code: {execution_result.returncode}"}
                
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Execution timeout exceeded"}
        except Exception as docker_error:
            return {"success": False, "error": str(docker_error)}
    
    def _analyze_test_results(self, dataset_entry: Dict[str, Any], logs_directory: Path) -> Dict[str, Any]:
        """Analyzes test results"""
        entry_instance_id = dataset_entry["instance_id"]
        expected_failing_tests = json.loads(dataset_entry["FAIL_TO_PASS"])
        expected_passing_tests = json.loads(dataset_entry["PASS_TO_PASS"])
        report_file_path = logs_directory / entry_instance_id / "report.json"
        
        if not report_file_path.exists():
            return {
                "validation_status": "report_not_found",
                "error": f"File {report_file_path} does not exist"
            }
        
        try:
            with open(report_file_path, 'r', encoding='utf-8') as report_file:
                test_report = json.load(report_file)
            
            instance_report_data = test_report.get(entry_instance_id, {})
            test_statuses = instance_report_data.get("tests_status", {})
            
            actual_failing_tests = test_statuses.get("FAIL_TO_PASS", {}).get("success", [])
            actual_passing_tests = test_statuses.get("PASS_TO_PASS", {}).get("success", [])
            
            failing_tests_match = set(expected_failing_tests) == set(actual_failing_tests)
            passing_tests_match = set(expected_passing_tests) == set(actual_passing_tests)
            
            problem_resolved = instance_report_data.get("resolved", False)
            
            if failing_tests_match and passing_tests_match and problem_resolved:
                validation_status = "success"
            else:
                validation_status = "test_mismatch"
            
            return {
                "validation_status": validation_status,
                "problem_resolved": problem_resolved,
                "failing_tests_match": failing_tests_match,
                "passing_tests_match": passing_tests_match,
                "expected_failing_tests": expected_failing_tests,
                "actual_failing_tests": actual_failing_tests,
                "expected_passing_tests": expected_passing_tests,
                "actual_passing_tests": actual_passing_tests
            }
            
        except Exception as analysis_error:
            return {
                "validation_status": "read_error",
                "error": str(analysis_error)
            }
    
    def print_summary_report(self, processing_results: Dict[str, Any]) -> None:
        """Prints summary report of results"""
        print("\n" + "="*70)
        print("📊 SWE-BENCH DATA VALIDATION REPORT")
        print("="*70)
        
        if "error" in processing_results:
            print(f"❌ Validation failed with error: {processing_results['error']}")
            return
        
        total_files = processing_results.get("total_processed", 0)
        successful_files = processing_results.get("success_count", 0)
        failed_files = processing_results.get("error_count", 0)
        success_rate = processing_results.get("success_percentage", 0.0)
        
        print(f"📁 Total files: {total_files}")
        print(f"✅ Successful: {successful_files}")
        print(f"❌ With errors: {failed_files}")
        print(f"📈 Success rate: {success_rate:.1f}%")
        
        individual_results = processing_results.get("individual_results", {})
        if individual_results:
            print(f"\n📋 Detailed results:")
            
            for filename, file_result in individual_results.items():
                if file_result.get("success", False):
                    validation_analysis = file_result.get("validation_analysis", {})
                    instance_id = file_result.get("instance_id", "unknown")
                    status = validation_analysis.get("validation_status", "unknown")
                    
                    if status == "success":
                        print(f"  ✅ {filename} ({instance_id}): All tests passed")
                    elif status == "test_mismatch":
                        print(f"  ⚠️  {filename} ({instance_id}): Some tests failed")
                    elif status == "report_not_found":
                        print(f"  📄 {filename} ({instance_id}): Report not found")
                    elif status == "read_error":
                        print(f"  🔍 {filename} ({instance_id}): Report read error")
                    else:
                        print(f"  ❓ {filename} ({instance_id}): Unknown status")
                else:
                    error_message = file_result.get("error", "unknown error")
                    print(f"  ❌ {filename}: {error_message}")
        
        # Final message
        if success_rate == 100.0:
            print(f"\n🎉 All files processed successfully!")
        elif success_rate >= 80.0:
            print(f"\n👍 Most files processed successfully")
        elif success_rate >= 50.0:
            print(f"\n⚖️  Half of files processed")
        else:
            print(f"\n😞 Most files failed with errors")


def main():
    """Main program function"""
    import argparse
    
    arg_parser = argparse.ArgumentParser(description="SWE-bench data points validator")
    arg_parser.add_argument("--data-dir", default="data_points", 
                           help="Folder with JSON data files")
    arg_parser.add_argument("--files", nargs="+", 
                           help="Specific file names for validation (without .json extension)")
    arg_parser.add_argument("--verbose", action="store_true", 
                           help="Verbose logging")
    
    parsed_args = arg_parser.parse_args()
    
    if parsed_args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    data_processor = DataPointProcessor(data_folder=parsed_args.data_dir)
    validation_results = data_processor.process_validation(parsed_args.files)
    data_processor.print_summary_report(validation_results)
    
    if "error" in validation_results:
        sys.exit(1)
    elif validation_results.get("success_percentage", 0) == 100.0:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()