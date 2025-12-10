# Requirements Document

## Introduction

This document specifies the requirements for a Data Forecasting Toolset that enables AI agents to perform time series forecasting on data for non-technical users. The toolset integrates two forecasting engines: Facebook Prophet for univariate time series forecasting with seasonality detection, and IBM Granite Time Series Model (TTM) for multivariate forecasting with inter-channel dependencies. The toolset is designed to handle messy real-world data, infer user intent from vague requests, and produce clear, actionable results. It integrates with the existing data provider schema and produces outputs compatible with the platform's chart visualization system.

## Glossary

- **Forecasting_Tool**: The backend tool class that exposes forecasting capabilities to AI agents
- **Prophet_Engine**: The Facebook Prophet-based forecasting component for univariate time series
- **Granite_Engine**: The IBM Granite Time Series Model (TTM) component for multivariate forecasting
- **Time_Series_Data**: A dataset containing timestamped observations with one or more value columns
- **Forecast_Result**: The output structure containing predicted values, confidence intervals, and metadata
- **Context_Length**: The number of historical data points used as input for prediction
- **Prediction_Length**: The number of future time steps to forecast
- **Seasonality**: Recurring patterns in time series data (daily, weekly, yearly)
- **Multivariate_Forecasting**: Forecasting multiple related time series simultaneously with inter-channel dependencies
- **Univariate_Forecasting**: Forecasting a single time series variable
- **Data_Cleaning**: The process of detecting and correcting messy, incomplete, or inconsistent data
- **Column_Inference**: Automatic detection of timestamp and value columns from data structure

## Requirements

### Requirement 1

**User Story:** As an AI agent, I want to perform univariate time series forecasting using Prophet, so that I can predict future values for single-variable datasets with automatic seasonality detection.

#### Acceptance Criteria

1. WHEN the Forecasting_Tool receives a request with a single target column and historical Time_Series_Data THEN the Forecasting_Tool SHALL invoke the Prophet_Engine to generate predictions
2. WHEN the Prophet_Engine processes Time_Series_Data THEN the Prophet_Engine SHALL automatically detect and model yearly, weekly, and daily seasonality patterns
3. WHEN the Prophet_Engine generates a forecast THEN the Prophet_Engine SHALL return predicted values with upper and lower confidence bounds
4. WHEN the Prophet_Engine receives a prediction_periods parameter THEN the Prophet_Engine SHALL generate forecasts for exactly that number of future time steps
5. IF the Time_Series_Data contains fewer than 2 data points THEN the Forecasting_Tool SHALL return an error indicating insufficient data

### Requirement 2

**User Story:** As an AI agent, I want to perform multivariate time series forecasting using IBM Granite TTM, so that I can predict multiple related variables simultaneously while capturing inter-channel dependencies.

#### Acceptance Criteria

1. WHEN the Forecasting_Tool receives a request with multiple target columns THEN the Forecasting_Tool SHALL invoke the Granite_Engine for multivariate forecasting
2. WHEN the Granite_Engine processes multivariate Time_Series_Data THEN the Granite_Engine SHALL model inter-channel dependencies between target columns
3. WHEN the Granite_Engine receives control_columns (exogenous variables) THEN the Granite_Engine SHALL incorporate those variables as additional predictive features
4. WHEN the Granite_Engine generates forecasts THEN the Granite_Engine SHALL return predictions for all specified target columns
5. WHEN the Granite_Engine processes data THEN the Granite_Engine SHALL apply standard scaling to normalize input features

### Requirement 3

**User Story:** As an AI agent, I want the forecasting tool to accept data in the existing data provider format, so that I can seamlessly use data from Yahoo Finance, and other providers for forecasting.

#### Acceptance Criteria

1. WHEN the Forecasting_Tool receives data with a timestamp column and value columns THEN the Forecasting_Tool SHALL parse the timestamp column as datetime objects
2. WHEN the Forecasting_Tool receives data from a data provider THEN the Forecasting_Tool SHALL validate that required columns exist before processing
3. WHEN the Forecasting_Tool receives data with missing values THEN the Forecasting_Tool SHALL handle missing values through interpolation or forward-fill
4. IF the Forecasting_Tool receives data without a valid timestamp column THEN the Forecasting_Tool SHALL return an error specifying the missing column requirement

### Requirement 3.1

**User Story:** As an AI agent helping non-technical users, I want the forecasting tool to automatically clean and prepare messy data, so that users can get forecasts without manual data preparation.

#### Acceptance Criteria

1. WHEN the Forecasting_Tool receives data with inconsistent date formats THEN the Forecasting_Tool SHALL attempt to parse dates using multiple common formats (ISO, US, European, Unix timestamps)
2. WHEN the Forecasting_Tool receives data with duplicate timestamps THEN the Forecasting_Tool SHALL aggregate duplicates by averaging values
3. WHEN the Forecasting_Tool receives data with outliers beyond 3 standard deviations THEN the Forecasting_Tool SHALL flag outliers and optionally cap extreme values
4. WHEN the Forecasting_Tool receives data with non-numeric value columns THEN the Forecasting_Tool SHALL attempt to convert strings to numbers by removing currency symbols, commas, and percentage signs
5. WHEN the Forecasting_Tool receives data with irregular time intervals THEN the Forecasting_Tool SHALL resample data to a regular frequency through interpolation
6. IF the Forecasting_Tool cannot automatically clean the data THEN the Forecasting_Tool SHALL return a descriptive error explaining the data quality issue

### Requirement 3.2

**User Story:** As an AI agent helping non-technical users, I want the forecasting tool to automatically detect column roles, so that users do not need to specify which columns contain timestamps or values.

#### Acceptance Criteria

1. WHEN the Forecasting_Tool receives data without explicit column mapping THEN the Forecasting_Tool SHALL scan column names for common timestamp indicators (date, time, timestamp, created_at, period)
2. WHEN the Forecasting_Tool receives data without explicit column mapping THEN the Forecasting_Tool SHALL identify numeric columns as potential value columns
3. WHEN the Forecasting_Tool detects multiple potential timestamp columns THEN the Forecasting_Tool SHALL select the column with the most datetime-parseable values
4. WHEN the Forecasting_Tool detects multiple numeric columns THEN the Forecasting_Tool SHALL use column names to infer primary target (price, value, amount, count, sales, revenue)
5. WHEN the Forecasting_Tool successfully infers column roles THEN the Forecasting_Tool SHALL include the inferred mapping in the response for user confirmation

### Requirement 4

**User Story:** As an AI agent, I want forecast results formatted for chart visualization, so that I can display predictions alongside historical data in the platform's UI.

#### Acceptance Criteria

1. WHEN the Forecasting_Tool generates a Forecast_Result THEN the Forecasting_Tool SHALL include historical values, predicted values, and confidence intervals in a chart-compatible format
2. WHEN the Forecasting_Tool returns forecast data THEN the Forecasting_Tool SHALL include timestamps for both historical and predicted periods
3. WHEN the Forecasting_Tool returns confidence intervals THEN the Forecasting_Tool SHALL provide upper and lower bounds as separate series
4. WHEN the Forecasting_Tool serializes results THEN the Forecasting_Tool SHALL output JSON-formatted data compatible with the existing tool result schema

### Requirement 5

**User Story:** As an AI agent, I want to configure forecasting parameters, so that I can tune predictions for different use cases and data characteristics.

#### Acceptance Criteria

1. WHEN the Forecasting_Tool receives a context_length parameter THEN the Forecasting_Tool SHALL use that number of historical data points for model input
2. WHEN the Forecasting_Tool receives a prediction_length parameter THEN the Forecasting_Tool SHALL generate forecasts for that number of future periods
3. WHEN the Forecasting_Tool receives a confidence_interval parameter THEN the Forecasting_Tool SHALL compute bounds at the specified confidence level
4. WHERE the user specifies seasonality_mode for Prophet THEN the Prophet_Engine SHALL use the specified mode (additive or multiplicative)
5. IF no configuration parameters are provided THEN the Forecasting_Tool SHALL use sensible defaults (context_length=512, prediction_length=96, confidence_interval=0.95)

### Requirement 5.1

**User Story:** As an AI agent helping non-technical users, I want to interpret vague forecasting requests, so that users can ask natural questions like "what will sales look like next month" without specifying technical parameters.

#### Acceptance Criteria

1. WHEN the Forecasting_Tool receives a natural language time horizon (next week, next month, next quarter, next year) THEN the Forecasting_Tool SHALL convert it to the appropriate prediction_length based on data frequency
2. WHEN the Forecasting_Tool receives data without explicit prediction_length THEN the Forecasting_Tool SHALL infer a reasonable forecast horizon based on data frequency and available history
3. WHEN the Forecasting_Tool receives a request mentioning "trend" THEN the Forecasting_Tool SHALL emphasize trend components in the response
4. WHEN the Forecasting_Tool receives a request mentioning "seasonal" or "pattern" THEN the Forecasting_Tool SHALL include seasonality decomposition in the response
5. WHEN the Forecasting_Tool generates forecasts THEN the Forecasting_Tool SHALL include a plain-language summary explaining the prediction in non-technical terms

### Requirement 6

**User Story:** As an AI agent, I want the forecasting tool to automatically select the appropriate engine based on input data, so that I get optimal predictions without manual engine selection.

#### Acceptance Criteria

1. WHEN the Forecasting_Tool receives data with a single target column and no control columns THEN the Forecasting_Tool SHALL default to the Prophet_Engine
2. WHEN the Forecasting_Tool receives data with multiple target columns THEN the Forecasting_Tool SHALL default to the Granite_Engine
3. WHEN the Forecasting_Tool receives data with control columns (exogenous variables) THEN the Forecasting_Tool SHALL default to the Granite_Engine
4. WHERE the user explicitly specifies an engine parameter THEN the Forecasting_Tool SHALL use the specified engine regardless of data characteristics

### Requirement 7

**User Story:** As a developer, I want the forecasting tool to follow the existing tool patterns, so that it integrates seamlessly with the agent framework.

#### Acceptance Criteria

1. WHEN the Forecasting_Tool is implemented THEN the Forecasting_Tool SHALL extend the Tool base class from core.agentpress.tool
2. WHEN the Forecasting_Tool defines methods THEN the Forecasting_Tool SHALL use the openapi_schema decorator for schema definitions
3. WHEN the Forecasting_Tool returns results THEN the Forecasting_Tool SHALL use the ToolResult class with success_response or fail_response methods
4. WHEN the Forecasting_Tool is registered THEN the Forecasting_Tool SHALL include tool_metadata with display_name, description, icon, and visibility settings

### Requirement 8

**User Story:** As an AI agent, I want to serialize and deserialize forecast models, so that I can save trained models and reuse them for future predictions without retraining.

#### Acceptance Criteria

1. WHEN the Forecasting_Tool trains a Prophet model THEN the Forecasting_Tool SHALL provide an option to serialize the model to JSON format
2. WHEN the Forecasting_Tool receives a serialized model THEN the Forecasting_Tool SHALL deserialize and use it for predictions without retraining
3. WHEN serializing a model THEN the Forecasting_Tool SHALL include model metadata (training date, data characteristics, parameters used)
4. WHEN deserializing a model THEN the Forecasting_Tool SHALL validate model compatibility with the current library version

### Requirement 9

**User Story:** As an AI agent helping non-technical users, I want to provide clear error messages and recovery suggestions, so that users understand what went wrong and how to fix it.

#### Acceptance Criteria

1. IF the Forecasting_Tool encounters insufficient data THEN the Forecasting_Tool SHALL explain the minimum data requirements in plain language and suggest data sources
2. IF the Forecasting_Tool cannot parse the data format THEN the Forecasting_Tool SHALL provide examples of acceptable formats
3. IF the Forecasting_Tool detects data quality issues THEN the Forecasting_Tool SHALL describe the specific issues found and offer to proceed with cleaned data
4. WHEN the Forecasting_Tool encounters an error THEN the Forecasting_Tool SHALL avoid technical jargon and provide actionable next steps
5. WHEN the Forecasting_Tool generates low-confidence predictions THEN the Forecasting_Tool SHALL warn the user about prediction uncertainty and explain contributing factors

### Requirement 10

**User Story:** As an AI agent helping non-technical users, I want to provide forecast explanations and insights, so that users understand what the predictions mean and what factors drive them.

#### Acceptance Criteria

1. WHEN the Forecasting_Tool generates a forecast THEN the Forecasting_Tool SHALL include a plain-language summary of the predicted trend direction (increasing, decreasing, stable)
2. WHEN the Forecasting_Tool detects seasonality THEN the Forecasting_Tool SHALL explain the seasonal patterns in user-friendly terms (e.g., "sales typically peak in December")
3. WHEN the Forecasting_Tool generates confidence intervals THEN the Forecasting_Tool SHALL explain what the range means (e.g., "we expect the value to be between X and Y with 95% confidence")
4. WHEN the Forecasting_Tool identifies significant changepoints THEN the Forecasting_Tool SHALL highlight when and why the trend changed
5. WHEN the Forecasting_Tool completes a multivariate forecast THEN the Forecasting_Tool SHALL explain which variables have the strongest relationships


### Requirement 11

**User Story:** As an AI agent, I want to prepare and transform data using Python scripts in the sandbox, so that I can handle complex data preparation tasks that require custom logic.

#### Acceptance Criteria

1. WHEN the Forecasting_Tool receives raw data requiring transformation THEN the Forecasting_Tool SHALL generate Python scripts to execute in the sandbox environment
2. WHEN the Forecasting_Tool generates data preparation scripts THEN the Forecasting_Tool SHALL use pandas for data manipulation and cleaning
3. WHEN the Forecasting_Tool executes sandbox scripts THEN the Forecasting_Tool SHALL save intermediate data files to the sandbox workspace for inspection
4. WHEN the Forecasting_Tool prepares data via sandbox THEN the Forecasting_Tool SHALL log each transformation step for transparency
5. WHEN the Forecasting_Tool encounters data from multiple sources THEN the Forecasting_Tool SHALL generate scripts to merge and align datasets by timestamp

### Requirement 11.1

**User Story:** As an AI agent, I want to provide reusable data preparation templates, so that common data transformations can be applied quickly without writing custom scripts each time.

#### Acceptance Criteria

1. WHEN the Forecasting_Tool detects CSV data with common issues THEN the Forecasting_Tool SHALL offer pre-built cleaning templates (date parsing, missing value handling, outlier removal)
2. WHEN the Forecasting_Tool receives financial data THEN the Forecasting_Tool SHALL offer templates for stock price normalization, returns calculation, and volume adjustment
3. WHEN the Forecasting_Tool receives sales data THEN the Forecasting_Tool SHALL offer templates for aggregation by period, currency conversion, and seasonal adjustment
4. WHEN the Forecasting_Tool applies a template THEN the Forecasting_Tool SHALL generate the corresponding Python script and execute it in the sandbox
5. WHEN the Forecasting_Tool completes data preparation THEN the Forecasting_Tool SHALL return a summary of transformations applied

### Requirement 11.2

**User Story:** As an AI agent, I want to validate prepared data before forecasting, so that I can ensure data quality meets forecasting requirements.

#### Acceptance Criteria

1. WHEN the Forecasting_Tool completes data preparation THEN the Forecasting_Tool SHALL validate that the timestamp column is monotonically increasing
2. WHEN the Forecasting_Tool completes data preparation THEN the Forecasting_Tool SHALL verify that value columns contain no remaining null values
3. WHEN the Forecasting_Tool completes data preparation THEN the Forecasting_Tool SHALL check that the data frequency is consistent (daily, weekly, monthly)
4. WHEN the Forecasting_Tool detects validation failures THEN the Forecasting_Tool SHALL report specific issues and suggest corrective scripts
5. WHEN the Forecasting_Tool validates data successfully THEN the Forecasting_Tool SHALL return data statistics (row count, date range, value ranges, detected frequency)

### Requirement 12

**User Story:** As an AI agent, I want to integrate forecasting with the sandbox file system, so that I can read data from uploaded files and save forecast results for download.

#### Acceptance Criteria

1. WHEN the Forecasting_Tool receives a file path in the sandbox THEN the Forecasting_Tool SHALL read data from CSV, Excel, or JSON files in the workspace
2. WHEN the Forecasting_Tool generates forecasts THEN the Forecasting_Tool SHALL save results to a CSV file in the sandbox workspace
3. WHEN the Forecasting_Tool saves forecast results THEN the Forecasting_Tool SHALL include both historical and predicted values in the output file
4. WHEN the Forecasting_Tool completes forecasting THEN the Forecasting_Tool SHALL provide the file path for user download
5. WHEN the Forecasting_Tool processes large datasets THEN the Forecasting_Tool SHALL stream data processing to avoid memory issues in the sandbox
