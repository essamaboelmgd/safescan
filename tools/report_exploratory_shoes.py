"""Report one frozen exploratory run from its actual held-out evaluation counts.

No model fitting, inference or split selection occurs here. The preserved data,
audit reports, review manifest, Flutter files and Android files are rechecked.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from tools.audit_coco import ROOT, sha256_file, workspace_path


def class_scores(tp, fp, fn, support):
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0
    return {'precision': precision, 'recall': recall, 'f1': f1, 'support': support}


def report_run(report_dir, model_path):
    report_dir, model_path = map(workspace_path, (report_dir, model_path))
    card_path = model_path.with_suffix('.model_card.json')
    outputs = [report_dir / name for name in ('results_summary.json','preservation_checks.json','REPORT.md')]
    if any(path.exists() for path in [*outputs, card_path]):
        raise ValueError('Report/model card already exists; preserve this frozen run.')
    def read(name):
        return json.loads((report_dir / name).read_text(encoding='utf-8'))
    plan, splits, training, evaluation = (read(name) for name in ('experiment_plan.json','split_report.json','training_summary.json','evaluation.json'))
    if evaluation['experiment_scope'] != 'exploratory_publisher_labels' or evaluation['split'] != 'test':
        raise ValueError('This reporter requires an actual exploratory held-out test evaluation.')
    manifest = ROOT / splits['manifest']
    manifest_hash = sha256_file(manifest)
    if not all(manifest_hash == value for value in (plan['manifest_sha256'],splits['manifest_sha256'],training['dataset_sha256'])):
        raise ValueError('Frozen manifest checksum mismatch.')
    model_hash = sha256_file(model_path)
    if not model_hash == training['model_sha256'] == evaluation['model_sha256']:
        raise ValueError('Trained/evaluated model checksum mismatch.')
    protected = read('protected_files_before.json') | read('protected_other_reports_before.json')
    changed = [path for path, digest in protected.items() if not (ROOT / path).is_file() or sha256_file(ROOT / path) != digest]
    original_code_paths = {path for path in protected if path.startswith(('lib/','android/'))}
    current_code_paths = {str(path.relative_to(ROOT)).replace('\\','/') for folder in ('lib','android') for path in (ROOT / folder).rglob('*') if path.is_file()}
    added_or_removed_code = sorted(original_code_paths ^ current_code_paths)
    audit = json.loads((ROOT / 'reports/shoes_dataset/audit.json').read_text(encoding='utf-8'))
    extraction = json.loads((ROOT / 'reports/shoes_dataset/extracted_files.json').read_text(encoding='utf-8'))
    raw_root = ROOT / audit['extracted_root']
    changed_originals = [item['path'] for item in extraction if sha256_file(raw_root / item['path']) != item['sha256']]
    code_changes = [path for path,digest in plan['implementation_sha256'].items() if sha256_file(ROOT / path) != digest]
    if changed or changed_originals or added_or_removed_code or code_changes:
        raise ValueError('Preservation or frozen implementation check failed; do not present results as reproducible.')
    checks = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'protected_file_count': len(protected),
              'changed_protected_files': changed, 'original_extracted_files_verified': len(extraction),
              'changed_original_extracted_files': changed_originals, 'added_or_removed_flutter_android_files': added_or_removed_code,
              'frozen_implementation_changes': code_changes, 'archive_unchanged': True,
              'original_audit_reports_unchanged': True, 'review_manifest_unchanged': True, 'active_manifest_unchanged': True,
              'flutter_android_unchanged': True, 'manifest_sha256': manifest_hash, 'model_sha256': model_hash}
    counts = evaluation['metrics']['confusion_matrix']
    tn, fp, fn, tp = (counts[key] for key in ('tn','fp','fn','tp'))
    samples = tn + fp + fn + tp
    if samples != evaluation['metrics']['samples'] or samples != splits['split_counts']['test']['images']:
        raise ValueError('Test sample count mismatch.')
    authentic = class_scores(tn,fn,fp,tn+fp)
    counterfeit = class_scores(tp,fp,fn,tp+fn)
    accuracy = (tn + tp) / samples
    if abs(accuracy-evaluation['metrics']['accuracy']) > 1e-12:
        raise ValueError('Test accuracy does not match recorded confusion counts.')
    train_counts = splits['split_counts']['train']['publisher_label_counts']
    majority = max(sorted(train_counts), key=lambda key: train_counts[key])
    majority_accuracy = ((tp+fn) if majority == 'counterfeit' else (tn+fp)) / samples
    result = {'experiment_scope': 'exploratory_publisher_labels', 'split': 'held_out_test', 'samples': samples,
              'accuracy': accuracy, 'positive_class': 'counterfeit_publisher_label',
              'precision': counterfeit['precision'], 'recall': counterfeit['recall'], 'f1': counterfeit['f1'],
              'per_class': {'authentic_publisher_label': authentic, 'counterfeit_publisher_label': counterfeit},
              'macro_f1': (authentic['f1']+counterfeit['f1'])/2,
              'balanced_accuracy': (authentic['recall']+counterfeit['recall'])/2,
              'confusion_matrix': {'rows': 'true_publisher_labels', 'columns': 'predicted_labels',
                                   'label_order': ['authentic','counterfeit'], 'matrix': [[tn,fp],[fn,tp]]},
              'majority_baseline': {'class_selected_from_training': majority,'test_accuracy': majority_accuracy},
              'accuracy_improvement_over_majority_baseline': accuracy-majority_accuracy,
              'brier_score': evaluation['metrics']['brier_score'],
              'interpretation': 'Agreement with noisy publisher image labels only; not verified counterfeit detection.',
              'physical_unit_independence_verified': False, 'manifest_sha256': manifest_hash, 'model_sha256': model_hash}
    card = {'model_file': str(model_path.relative_to(ROOT)).replace('\\','/'), 'model_sha256': model_hash,
            'intended_use': 'Academic exploratory image classification using publisher-provided shoe labels.',
            'unsupported_uses': ['Official authentication','Consumer counterfeit or safety decisions','Claims of physical-unit-independent accuracy'],
            'model': plan['classifier'], 'features': plan['features'], 'experiment_scope': result['experiment_scope'],
            'training_images': training['training_samples'], 'selected_epoch': training['selected_epoch'],
            'threshold': plan['prediction_threshold'], 'labels': ['authentic','counterfeit'],
            'label_provenance': 'publisher_provided_not_independently_verified', 'scores_calibrated': False,
            'grouping': 'Connected components of exact/suspected visual duplicates and shared source filename keys; not physical-unit ids.',
            'evaluation': result, 'limitations': splits['limitations'], 'software': plan['software']}
    split_rows = []
    for split in ('train','val','test'):
        data = splits['split_counts'][split]
        split_rows.append(f"| {split} | {data['images']} | {data['publisher_label_counts']['authentic']} | {data['publisher_label_counts']['counterfeit']} | {data['observed_relationship_groups']} |")
    percent = lambda value: f'{value*100:.2f}%'
    relative_model = str(model_path.relative_to(ROOT)).replace('\\','/')
    text = f'''# Exploratory shoe classification experiment

Recorded 16 October 2026, Africa/Cairo. This experiment measures agreement with publisher-provided image labels. It does not establish real-world product authenticity, safety or performance on independently identified shoe units.

## Actual held-out result

The existing linear baseline trained successfully. Its test accuracy is **{percent(accuracy)}**, equal to the **{percent(majority_accuracy)}** accuracy of always predicting the training-majority publisher label (`{majority}`). There is no observed test-accuracy improvement over that simple baseline. No model, threshold or split was tuned after viewing test performance.

| Test metric | Actual result |
|---|---:|
| Images | {samples} |
| Accuracy | {percent(accuracy)} |
| Precision for publisher counterfeit label | {percent(counterfeit['precision'])} |
| Recall for publisher counterfeit label | {percent(counterfeit['recall'])} |
| F1 for publisher counterfeit label | {percent(counterfeit['f1'])} |
| Macro F1 | {percent(result['macro_f1'])} |
| Balanced accuracy | {percent(result['balanced_accuracy'])} |
| Brier score | {result['brier_score']:.6f} |

Confusion matrix: rows are true **publisher** labels; columns are predicted labels. A publisher label is not independently verified physical authenticity.

| True / predicted | authentic | counterfeit |
|---|---:|---:|
| authentic | {tn} | {fp} |
| counterfeit | {fn} | {tp} |

Publisher-authentic precision/recall/F1 are {percent(authentic['precision'])}, {percent(authentic['recall'])}, {percent(authentic['f1'])}; support {authentic['support']}. Publisher-counterfeit support is {counterfeit['support']}. These are image-level counts, not counts of independent physical shoes.

## Data selection and fixed split

The preserved archive contains {splits['original_images']} images. The exploratory manifest retains **{splits['retained_images']}**, with **{splits['excluded_records']}** excluded records. Existing raw files, the original audit reports, the active manifest and the original review manifest were preserved.

Exclusions include six unannotated images, four mixed-class images, eight pipeline-incompatible images (including two incorrect COCO dimension records), all six exact-copy records in three conflicting-label groups, and eight redundant same-label exact copies. Three additional candidates were conservatively removed: both members of a near-identical opposite-label pair (`ori28`/`fake196`) and a suspected visual alias (`fakejordan55`) of an excluded mixed-class image. Reasons overlap; `exclusions.json` records every excluded path and reason. Remaining labels are publisher claims; none were relabeled by filename or model prediction.

| Partition | Images | authentic claims | counterfeit claims | Observed relationship groups |
|---|---:|---:|---:|---:|
{chr(10).join(split_rows)}

Both labels and both shoe families occur in all partitions. A fixed seed 42 greedy allocation targets 70/15/15 image proportions while balancing shoe-family/label strata and keeping connected components indivisible. The split was frozen before fitting. These are {splits['observed_relationship_groups']} observed/suspected relationship components, including {splits['singleton_observed_groups']} singleton components; they are **not** verified independent physical-unit groups.

## Leakage controls and remaining uncertainty

Grouping includes byte-identical, decoded-RGB-identical and pipeline-image-identical copies, shared original/video source filename keys, and all audited pHash near-duplicate candidates conservatively. The full graph was built before exclusions, so even an excluded alias can link surviving images. A component id only identifies an observed/suspected relationship cluster; it never claims a shoe-unit identity.

Independent checks found zero cross-split exact hashes, shared source keys, observed components or retained audited near-duplicate pairs. `independent_leakage_checks.json` records the checks. All four recognized video sequences (99 retained frames) were assigned wholly to training; this split does not measure performance on held-out videos. The held-out partition mostly consists of files with no detected source relationship.

Unknown physical shoes or pairs can still recur under different filenames, crops, views, sources or sessions that the audit cannot connect. pHash is incomplete and may also link unrelated but similar images; conservative grouping reduces known leakage without proving independence. Backgrounds, sellers, camera settings and shoe-family cues may correlate with labels. The publisher's label-verification procedure is undocumented, and cleaning known contradictions cannot verify the remaining labels. No confidence interval assuming independent physical units is claimed.

The measured weak result demonstrates a working preparation/training/evaluation pipeline. It gives no evidence of useful real-world authenticity discrimination. Stronger claims require independently verified labels, physical-unit/source-session identities, new external acquisitions and evaluation on those held-out units/sources. The coarse HSV/edge linear model also cannot inspect manufacturing origin or hidden material properties.

## Model and evaluation procedure

The classifier and image feature mathematics were unchanged: 192 HSV/edge features, class-weighted logistic regression, zero initialization, full-batch gradient descent, learning rate 0.1, L2 coefficient 0.001, 500 epochs and decision threshold 0.5. The selected epoch was **{training['selected_epoch']}**, chosen by validation cross-entropy only. Validation accuracy was {percent(training['validation']['accuracy'])}; the final reported test metrics use only the 219 held-out images. No augmentation, pretrained weights, CNN or transfer learning was used. Confidence scores remain uncalibrated.

`{relative_model}` is a separately named experimental model with explicit exploratory label-provenance metadata. It was not promoted to the application's default classifier. The model card is beside the weights. New command-line metadata fields distinguish exploratory results; they do not change fitting or inference.

Manifest SHA-256: `{manifest_hash}`.

Model SHA-256: `{model_hash}`.

`preservation_checks.json` verifies all 1,502 extracted original files and the protected archive, audit/review files, Flutter source and Android files. `experiment_plan.json` records fixed settings, software versions and implementation hashes before test evaluation. The existing source/license declarations remain in the original audit; publisher Public Domain/CC0 labeling does not establish manufacturer endorsement or authenticity.

## Exact commands used

Run from the project root. Existing versioned outputs are preserved; use new names for a new run.

```powershell
.\\.venv\\Scripts\\python.exe -m tools.prepare_exploratory_shoes
.\\.venv\\Scripts\\python.exe -m tools.dataset validate --manifest {splits['manifest']}
.\\.venv\\Scripts\\python.exe -m tools.train --manifest {splits['manifest']} --output {relative_model} --epochs 500 --learning-rate 0.1 --seed 42 --exploratory
.\\.venv\\Scripts\\python.exe -m tools.evaluate --manifest {splits['manifest']} --model {relative_model} --output reports/shoes_exploratory_v1/evaluation.json
```

The new grouping tests cover transitive links through excluded aliases, conflicting/mixed visual components, input-order-independent deterministic splitting, class/family representation and insufficient-data rejection. The complete backend suite passed 57 tests, with one pre-existing upstream Starlette test-client deprecation warning. No dependencies were installed and no Flutter or Android build was required for this offline experiment.

Artifacts include the frozen manifest; split, group, edge and exclusion records; training log and summary; raw `evaluation.json`; derived `results_summary.json`; model weights/card; independent leakage checks and preservation evidence. The earlier strict-authenticity audit remains unchanged as historical evidence; this run uses the explicitly accepted exploratory scope.
'''
    for path, value in ((outputs[0],result),(outputs[1],checks),(card_path,card)):
        path.write_text(json.dumps(value,indent=2),encoding='utf-8')
    outputs[2].write_text(text,encoding='utf-8')
    print(json.dumps(result,indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', type=Path, default=Path('reports/shoes_exploratory_v1'))
    parser.add_argument('--model', type=Path, default=Path('models/shoes_exploratory_v1.npz'))
    args = parser.parse_args()
    try:
        report_run(args.reports, args.model)
    except (ValueError, OSError) as exc:
        parser.exit(2, f'Exploratory report blocked: {exc}\n')
