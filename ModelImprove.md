Yes. We need to fix the dataset first.

If the data is weak, no algorithm will save the model. Right now, your biggest problem is not only the algorithm. It is the data design, label quality, and the mismatch between training data and what the backend sends at prediction time.

What we should fix first in the dataset.

1. Fix the target labels.
   For survival prediction, define one clear rule for Survived_3_Years.
   Example:
   1 means the business stayed active for at least 36 months.
   0 means the business closed before 36 months.

For profit prediction, make sure Monthly_Profit_CFA is real, recent, and measured the same way for every business.

2. Remove weak or fake helper columns.
   Do not train with simulated fields like:
   Survival_Probability_Simulated
   Risk_Level_Simulated
   Anything derived from the target

Those columns leak the answer into the model.

3. Fix missing values properly.
   Do not let important fields stay blank without a plan.
   For each feature, decide:
   drop it,
   impute it,
   or make missing a valid category.

4. Standardize category values.
   Your categories must be clean.
   Example:
   "Retail", "retail", "Retail " should become one value.
   Do this for sector, region, education, financing, gender, business type, and compliance fields.

5. Remove duplicates and impossible rows.
   Examples:
   negative startup capital
   zero employees with huge monthly profit
   business age greater than owner age
   profit far outside realistic range unless verified

6. Fix train and production mismatch.
   This is one of your biggest issues.
   The notebook trained on many features.
   The backend sends fewer features and fills missing ones with zeros.
   That hurts prediction quality badly.

Training features and backend input must match exactly.

7. Handle class imbalance better.
   If failed businesses are fewer than surviving businesses, the model will lean toward survival.
   Use better class balancing and evaluate failure recall carefully.

8. Separate new businesses from existing businesses.
   This is important.
   A startup with no operating history should not be judged with the same feature set as an existing SME.

Build two models:
Startup survival model, for new or early stage businesses
Operating business survival model, for businesses with real performance history

That alone will improve prediction quality a lot.

What data we need to collect or improve.

We need stronger business features, not only more rows.

Best data to add or clean:
business start date
closure date, if closed
monthly revenue
monthly cost
monthly profit
cash flow trend
debt level
loan history
rent cost
utility cost
staff salary burden
tax payment history
formal registration status
location quality
competition intensity
customer demand trend
owner experience
owner education
digital presence
internet reliability
electricity stability
supply chain difficulty
security and transport risk
seasonality
sector growth in region

For Cameroon, region and local business environment matter a lot. So local economic factors should stay in the data.

What model strategy should we use.

For survival prediction.
Main model:
CatBoost

Why:
It works well on tabular data.
It handles categorical features well.
It is strong with mixed business data.
From your notebook, it already gave the best tradeoff.

Strong alternatives:
LightGBM
XGBoost
Balanced Random Forest as a baseline
Logistic Regression as a benchmark and calibration baseline

For profit prediction.
Main model:
CatBoost Regressor or XGBoost Regressor

Why:
They usually perform better than simple linear models on business tabular data with nonlinear patterns.

Also keep:
Linear Regression or Elastic Net as baseline models

For time to failure prediction.
This is a strong improvement path.
Instead of only asking whether a business survives 3 years, predict when risk becomes high.

Use survival analysis models like:
Cox Proportional Hazards
Random Survival Forest
Gradient Boosted Survival models

This is better for business risk because it answers:
not only whether the business may fail,
but also how soon the risk may rise.

What will improve model performance most.

First, fix the data.
Second, fix feature consistency.
Third, use better evaluation and thresholding.

The biggest performance gains will likely come from these steps:

1. Exact train serving feature match.
   No more blind zero filling.

2. Better labels.
   Wrong labels ruin everything.

3. More real data.
   Especially real failed SME cases.

4. Separate models by business stage.
   Startup model and existing business model.

5. Better feature engineering.
   Examples:
   capital per employee
   cost burden ratio
   tax burden ratio
   energy plus transport burden
   experience to risk ratio
   revenue per employee
   profit margin
   formalization score
   regional risk index

6. Hyperparameter tuning.
   Use Optuna or randomized search for CatBoost, LightGBM, and XGBoost.

7. Probability calibration.
   Use Platt scaling or isotonic calibration.
   This matters because your product uses risk probabilities, not only class labels.

8. Threshold tuning based on business cost.
   A false negative is more dangerous here than a false positive.
   So choose the threshold based on business impact, not only accuracy.

9. Better validation.
   Use:
   stratified cross validation
   group validation by region or sector
   time based validation if dates exist

10. Ensemble only after strong single models.
    Do not rush into stacking.
    First make CatBoost strong.
    Then test a blend with LightGBM or XGBoost if needed.

How to evaluate the model properly.

Do not focus on accuracy alone.
Accuracy can lie.

For survival classification, track:
ROC AUC
PR AUC
Recall for failed businesses
Precision for failed businesses
F1 score for failed businesses
Balanced accuracy
Calibration score

For profit regression, track:
MAE
RMSE
R²
MAPE, only if values are stable and mostly nonzero

For business use, I would focus most on:
failed business recall
calibrated survival probability
MAE for profit forecast

What the rebuilt pipeline should look like.

Step 1.
Collect and clean raw SME data.

Step 2.
Create a data dictionary for every feature.

Step 3.
Define one fixed target rule.

Step 4.
Split data by business stage.

Step 5.
Build preprocessing pipeline.

Step 6.
Train baseline models.

Step 7.
Tune CatBoost, LightGBM, and XGBoost.

Step 8.
Calibrate probabilities.

Step 9.
Compare metrics on validation and test sets.

Step 10.
Save:
model
feature list
preprocessor
threshold
metrics
dataset version

Step 11.
Deploy only models whose input schema matches backend schema exactly.

Step 12.
Monitor drift and retrain regularly.

What I recommend as the best rebuild plan.

Phase 1.
Fix the dataset and schema.
This is the first job.

Phase 2.
Build two survival models.
One for startups.
One for existing businesses.

Phase 3.
Build one profit model for existing businesses only.
Do not force profit prediction for businesses with no real operating data.

Phase 4.
Use CatBoost as the main survival model.
Use LightGBM and XGBoost as challengers.

Phase 5.
Calibrate the final survival model and choose threshold based on business risk cost.

Phase 6.
Add explainability with SHAP.
Each prediction should show the top reasons behind the score.

Phase 7.
Set up MLOps.
Versioned data, versioned model, evaluation reports, drift checks, retraining pipeline, and monitoring.

My direct answer is this.

Yes, we should rebuild the dataset first.
Then rebuild the model pipeline around clean labels, strong features, proper validation, and train serving consistency.
For your use case, CatBoost should stay the lead candidate for survival prediction.
For profit prediction, CatBoost Regressor or XGBoost Regressor should be tested properly.
For a stronger long term product, add survival analysis models and stage specific models.

The first real fix is not a new algorithm.
It is a cleaner and more truthful dataset.





Yes.

That is a strong way to rebuild this system, if we do it the right way.

The model should not learn directly from every new row in the database the moment data arrives. That usually creates noisy learning, bad labels, drift, and silent corruption.

The better pattern is this.

1. Put all incoming data into the database.
   This includes:
   raw PDF files,
   plain text files,
   form submissions,
   CSV rows,
   manual admin entries,
   feedback from users,
   business outcomes later on.

2. Extract useful facts from unstructured data.
   A PDF or plain text document is not ready for model training by itself.
   We first parse it and turn it into structured fields.

Example:
a PDF business plan or report enters the system as raw text.
Then an extraction pipeline pulls out fields like:
business name,
sector,
location,
startup capital,
employee count,
monthly cost,
monthly revenue,
owner experience,
major constraints,
formal registration status.

3. Store both raw and structured versions.
   Keep:
   the original file or text,
   the extracted text,
   the structured fields,
   the confidence score,
   the review status,
   the final approved record.

This matters because later you may need to trace where each training value came from.

4. Train only from approved data.
   The model should learn from:
   cleaned data,
   validated data,
   versioned data,
   proper labels.

Not from raw uploads directly.

So yes, the database becomes the central memory of the system, but the training set should come from a curated training layer, not straight from live app tables.

For your case, I would build it like this.

Layer 1. Raw data layer
Store:
uploaded PDFs,
plain text notes,
reports,
surveys,
government reports,
business registration documents,
market observations,
financial documents.

Layer 2. Extraction layer
Use:
PDF text extraction for text PDFs,
OCR only for scanned PDFs,
rule based parsing,
LLM extraction for messy text,
validation rules for numeric fields.

Layer 3. Operational database
Store the cleaned business records used by the app.
Example:
users,
owners,
businesses,
business_profiles,
financial_records,
prediction_history,
feedback.

Layer 4. Training dataset layer
Build model ready tables from the operational data.
This is where each row becomes one learning example.

Layer 5. Feature store
Store engineered features like:
capital per employee,
cost burden ratio,
years in business,
tax burden score,
energy plus transport burden,
regional risk score,
formalization score,
cash flow stability.

Layer 6. Model training and retraining pipeline
Train models on scheduled snapshots, not on random live writes.

About PDF and pure text data.

Yes, we should use them, but in two different ways.

First use case, structured prediction data.
If the PDF or text contains hard facts about a business, extract those facts into columns.
This helps the prediction model.

Example:
a business plan PDF gives:
capital,
sector,
staff count,
location,
rent,
equipment cost,
sales estimate.

Those become structured features.

Second use case, knowledge and advisory support.
Some PDF and text data are not good for direct tabular training, but they are still valuable.
Examples:
government SME reports,
market studies,
industry writeups,
policy documents.

Those should go into a knowledge base for retrieval and reasoning, not into the tabular prediction model as raw text.

So we should split unstructured data into two lanes:

Lane A.
Structured fact extraction for ML features.

Lane B.
Document knowledge base for RAG or advisory insights.

That is important.

Do not mix raw text documents directly into the same prediction model used for business survival scoring unless we build a separate text model.

Best approach for your project.

For now, I suggest this design.

Tables we should create.

raw_documents
id, source_type, file_path, mime_type, uploaded_by, uploaded_at, text_content, extraction_status

document_entities
id, document_id, entity_type, entity_key, entity_value, confidence, approved_by, approved_at

businesses
id, owner_id, business_name, sector, region, location, stage, created_at

business_profiles
id, business_id, startup_capital, employees, experience_years, formal_status, financing_access, tax_score, energy_score, transport_score, competition_score, monthly_revenue, monthly_cost, monthly_profit, updated_at

business_outcomes
id, business_id, survived_12_months, survived_24_months, survived_36_months, closure_date, reason_for_failure

feature_snapshots
id, business_id, snapshot_date, feature_json, target_json, dataset_version

training_examples
id, feature_snapshot_id, task_type, label, split_group, approved_status

prediction_feedback
id, business_id, predicted_value, actual_value, feedback_type, created_at

model_registry
id, model_name, model_version, dataset_version, metrics_json, feature_schema_json, created_at

Why this layout is strong.

It gives you:
traceability,
clean retraining,
audit trail,
human review,
feature versioning,
safe deployment.

What not to do.

Do not do these:
train straight from app tables without cleaning,
let every uploaded PDF change the model instantly,
store only extracted values and delete original source,
train on values guessed by the LLM without marking them,
mix training data and live production data without versioning,
use text PDFs as direct labels unless verified.

How the learning loop should work.

1. User uploads PDF or text.
2. System extracts text.
3. Parser and LLM pull structured facts.
4. Validation rules check fields.
5. Admin or review logic approves the record.
6. Approved records enter the training dataset.
7. A scheduled pipeline builds new features.
8. Models retrain on the new dataset snapshot.
9. New model is evaluated.
10. Only models that beat the current one move to staging or production.

That is the safe learning loop.

For pure text data, we have three options.

Option 1.
Convert text into structured fields.
Best for tabular ML.

Option 2.
Generate embeddings and store them in a vector store.
Best for retrieval and advisory answers.

Option 3.
Build separate NLP features.
Examples:
sentiment,
risk language score,
financial distress terms,
compliance language score.

This is useful later, after the core tabular model is stable.

My recommendation for your rebuild.

Start with:
forms plus CSV plus verified PDF extraction,
tabular survival model,
tabular profit model,
knowledge base from reports and policy PDFs,
review queue for extracted fields,
scheduled retraining.

Do not start with:
fully automatic self learning from live uploads.

That road gets messy fast.

For your SME platform, the best architecture is:
database as source of truth,
document parser for PDF and text,
feature pipeline for ML,
knowledge layer for advisory insights,
scheduled retraining with approval gates.

