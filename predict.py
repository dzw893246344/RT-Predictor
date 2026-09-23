# %%
import numpy as np
import pandas as pd
import deepchem as dc
from rdkit import Chem
import warnings
import argparse
import json
import os
from deepchem.models.optimizers import Adam

# 忽略可能的警告信息
warnings.filterwarnings("ignore")


class AttentiveFPModelWrapper:
    """
    AttentiveFP模型包装器，自动保存和加载模型配置
    解决DeepChem模型加载时需要手动配置相同架构的问题
    """

    def __init__(self, model_dir="AttentiveModel"):
        self.model_dir = model_dir
        self.config_file = os.path.join(model_dir, "model_config.json")
        self.model = None

    def load_model(self):
        """从配置文件加载模型"""
        if not os.path.exists(self.config_file):
            raise FileNotFoundError(
                f"配置文件不存在: {self.config_file}\n"
                f"请确保模型是使用AttentiveFPModelWrapper训练并保存的"
            )

        # 读取配置
        with open(self.config_file, "r", encoding="utf-8") as f:
            config = json.load(f)

        print(f"从配置文件加载模型: {self.config_file}")

        # 移除非模型参数的配置项
        config.pop("parameter_notes", None)
        nb_epoch = config.pop("nb_epoch", None)

        # 恢复optimizer对象
        optimizer_name = config.get("optimizer", "Adam")
        if optimizer_name == "Adam":
            config["optimizer"] = Adam()
        else:
            print(f"警告：未识别的optimizer: {optimizer_name}，使用默认Adam")
            config["optimizer"] = Adam()

        # 打印加载的配置
        print(f"加载的模型配置：")
        print(f"  - n_tasks: {config['n_tasks']}")
        print(f"  - num_layers: {config['num_layers']}")
        print(f"  - graph_feat_size: {config['graph_feat_size']}")
        print(f"  - dropout: {config.get('dropout', 'N/A')}")
        if nb_epoch:
            print(f"  - 训练轮数: {nb_epoch}")

        # 创建模型并恢复权重
        self.model = dc.models.AttentiveFPModel(**config)
        self.model.restore()
        print("模型权重恢复成功！")

        return self.model

    def get_model_info(self):
        """获取模型配置信息"""
        if os.path.exists(self.config_file):
            with open(self.config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            return config
        return None

    @staticmethod
    def quick_load(model_dir="AttentiveModel"):
        """
        快速加载模型的静态方法（一行代码加载）

        使用示例:
            model = AttentiveFPModelWrapper.quick_load("AttentiveModel")
        """
        wrapper = AttentiveFPModelWrapper(model_dir)
        return wrapper.load_model()


def load_model(model_dir):
    """
    加载AttentiveFP模型（使用包装器自动获取配置）

    参数:
        model_dir: 模型目录

    返回:
        已加载的模型和配置信息
    """
    print(f"加载模型: {model_dir}")
    print("-" * 50)

    # 使用包装器加载模型
    wrapper = AttentiveFPModelWrapper(model_dir)
    model = wrapper.load_model()

    # 获取模型配置信息
    model_info = wrapper.get_model_info()

    print("-" * 50)
    return model, model_info


def read_csv_robust(path, **kwargs):
    """尝试多种编码读取CSV，兼容Excel导出（可能为GBK/带BOM）"""
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return pd.read_csv(path, encoding="utf-8", **kwargs)


def load_data(input_file, smiles_column):
    """
    加载数据并处理缺失的SMILES

    参数:
        input_file: 输入CSV文件路径
        smiles_column: SMILES所在的列名

    返回:
        清理后的DataFrame
    """
    print(f"读取输入文件: {input_file}")
    df = read_csv_robust(input_file)

    # 记录原始数据条数
    original_count = len(df)
    print(f"原始数据: {original_count} 条记录")

    # 删除SMILES为空的行
    df = df.dropna(subset=[smiles_column])
    df = df[df[smiles_column].str.strip() != ""]

    # 记录清理后的数据条数
    cleaned_count = len(df)
    if cleaned_count < original_count:
        print(f"删除了 {original_count - cleaned_count} 条SMILES为空的记录")
    print(f"清理后数据: {cleaned_count} 条记录")

    return df


def setup_featurizer(smiles_column):
    """
    设置特征化器和加载器

    参数:
        smiles_column: SMILES所在的列名

    返回:
        CSVLoader实例
    """
    tasks = ["RT"]  # 任务名称，仅用于特征化过程
    featurizer = dc.feat.MolGraphConvFeaturizer(use_edges=True)

    # 创建CSVLoader实例
    loader = dc.data.CSVLoader(
        tasks=tasks, feature_field=smiles_column, featurizer=featurizer
    )

    return loader


def featurize_molecule(smiles, loader):
    """
    特征化单个分子

    参数:
        smiles: SMILES字符串
        loader: CSVLoader实例

    返回:
        特征化后的数据和状态（成功/失败）
    """
    # 检查SMILES是否有效
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None, False, "无效SMILES"

    # 创建单个分子的DataFrame
    single_mol_df = pd.DataFrame(
        {
            loader.feature_field: [smiles],
            "RT": [0.0],  # 占位符值，预测模式下不会使用
        }
    )

    # 特征化处理
    try:
        X, valid_inds = loader._featurize_shard(single_mol_df)

        # 检查特征化是否成功
        if len(valid_inds) == 0 or not any(valid_inds):
            return None, False, "特征化失败"

        return X, True, None

    except Exception as e:
        return None, False, str(e)


def predict_molecule_rt(model, X, smiles, min_rt=1.0, max_rt=6.0):
    """
    预测单个分子的保留时间

    参数:
        model: 已加载的模型
        X: 特征化后的数据
        smiles: SMILES字符串
        min_rt: 保留时间下限
        max_rt: 保留时间上限

    返回:
        预测的保留时间
    """
    # 创建数据集对象
    ids = np.array([smiles])
    dataset = dc.data.NumpyDataset(X=X, ids=ids)

    # 预测
    prediction = model.predict(dataset)

    # 将预测值限制在指定范围内
    bounded_prediction = np.clip(prediction, min_rt, max_rt)[0][0]

    return bounded_prediction


def process_data(
    df,
    model,
    loader,
    smiles_column,
    output_column,
    min_rt=1.0,
    max_rt=6.0,
    batch_size=10,
):
    """
    处理数据并预测保留时间

    参数:
        df: 输入数据DataFrame
        model: 已加载的模型
        loader: CSVLoader实例
        smiles_column: SMILES所在的列名
        output_column: 输出保留时间的列名
        min_rt: 保留时间下限
        max_rt: 保留时间上限
        batch_size: 报告进度的批次大小

    返回:
        处理后的DataFrame和错误记录
    """
    total_compounds = len(df)
    predicted_rt_list = []
    error_records = []

    print(f"\n开始预测，共 {total_compounds} 个分子...")
    print("-" * 50)

    # 逐个处理每个SMILES
    for i, row in df.iterrows():
        try:
            smiles = row[smiles_column]

            # 特征化分子
            X, success, error_msg = featurize_molecule(smiles, loader)

            if not success:
                print(
                    f"处理失败 ({i + 1}/{total_compounds}): {smiles}, 原因: {error_msg}"
                )
                predicted_rt_list.append(None)
                error_records.append({"Index": i, "SMILES": smiles, "Error": error_msg})
                continue

            # 预测保留时间
            rt = predict_molecule_rt(model, X, smiles, min_rt, max_rt)
            predicted_rt_list.append(rt)

            # 打印进度
            if (i + 1) % batch_size == 0 or i == 0 or i == total_compounds - 1:
                print(
                    f"处理进度: {i + 1}/{total_compounds}, 当前SMILES: {smiles}, 预测RT: {rt:.4f}"
                )

        except Exception as e:
            smiles = row.get(smiles_column, "无法获取SMILES")
            print(f"处理失败 ({i + 1}/{total_compounds}): {smiles}, 错误: {str(e)}")
            predicted_rt_list.append(None)
            error_records.append({"Index": i, "SMILES": smiles, "Error": str(e)})

    # 将预测结果添加到DataFrame
    result_df = df.copy()
    result_df[output_column] = predicted_rt_list
    def is_customizable(rt):
        if rt is None:
            return '未知'
        return '是' if 1.0 <= rt <= 5.0 else '否'

    result_df['是否可定制'] = [is_customizable(x) for x in result_df[output_column]]
    del result_df[output_column]
    # 统计成功率
    success_count = total_compounds - len(error_records)
    print("-" * 50)
    print(
        f"\n成功处理: {success_count}/{total_compounds} SMILES ({success_count / total_compounds * 100:.1f}%)"
    )

    # 如果有错误，创建错误记录DataFrame
    error_df = pd.DataFrame(error_records) if error_records else None

    return result_df, error_df


def save_results(result_df, error_df, output_file, error_file):
    """
    保存结果和错误记录

    参数:
        result_df: 结果DataFrame
        error_df: 错误记录DataFrame
        output_file: 输出文件路径
        error_file: 错误记录文件路径
    """
    # 保存结果（utf-8-sig 带 BOM，保证 Excel/Office 打开不乱码）
    result_df.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"结果已保存到 {output_file}")

    # 如果有错误，保存错误记录
    if error_df is not None and not error_df.empty:
        error_df.to_csv(error_file, index=False, encoding="utf-8-sig")
        print(f"处理失败: {len(error_df)} SMILES，详情已保存到 {error_file}")


def main(args):
    """
    主函数

    参数:
        args: 命令行参数或参数对象
    """
    print("=" * 60)
    print("    AttentiveFP 保留时间预测系统")
    print("=" * 60)

    # 加载模型（使用包装器，自动获取配置）
    model, model_info = load_model(args.model_dir)

    # 显示模型训练信息（如果有）
    if model_info and "parameter_notes" in model_info:
        print("\n模型参数说明：")
        for key, note in model_info["parameter_notes"].items():
            if key in [
                "num_layers",
                "graph_feat_size",
                "dropout",
                "batch_size",
                "learning_rate",
            ]:
                print(f"  - {key}: {note}")

    print("\n" + "=" * 60)

    # 加载并清理数据
    df = load_data(args.input_file, args.smiles_column)

    # 设置特征化器
    loader = setup_featurizer(args.smiles_column)

    # 处理数据
    result_df, error_df = process_data(
        df,
        model,
        loader,
        args.smiles_column,
        args.output_column,
        min_rt=args.min_rt,
        max_rt=args.max_rt,
        batch_size=args.batch_size,
    )

    # 保存结果
    print("\n" + "=" * 60)
    save_results(result_df, error_df, args.output_file, args.error_file)
    print("=" * 60)
    print("预测完成！")


# ===============================================
# 命令行参数支持（可选）
# ===============================================


def parse_arguments():
    """
    解析命令行参数

    返回:
        解析后的参数
    """
    parser = argparse.ArgumentParser(
        description="使用AttentiveFP模型预测化合物的保留时间",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python predict.py --input_file data.csv --output_file results.csv
  python predict.py --model_dir MyModel --min_rt 0.5 --max_rt 10.0
        """,
    )

    # 文件参数
    parser.add_argument(
        "--input_file",
        type=str,
        default="data/IS_rtttt.csv",
        help="输入CSV文件路径",
    )
    parser.add_argument(
        "--output_file",
        type=str,
        default="predicted_RT_results.csv",
        help="输出CSV文件路径",
    )
    parser.add_argument(
        "--error_file", type=str, default="error_smiles.csv", help="错误记录CSV文件路径"
    )
    parser.add_argument(
        "--model_dir",
        type=str,
        default="./AttentiveModel_RP_6min",#把RP_6min改成HILIC_6min就是另一个类型
        help="模型目录（包含model_config.json）",
    )

    # 列名参数
    parser.add_argument(
        "--smiles_column", type=str, default="IsomericSMILES", help="SMILES所在的列名"
    )
    parser.add_argument(
        "--output_column", type=str, default="Predicted_RT", help="输出保留时间的列名"
    )

    # 预测参数（模型参数将自动从配置文件读取）
    parser.add_argument("--min_rt", type=float, default=0.0, help="保留时间下限")
    parser.add_argument("--max_rt", type=float, default=6.0, help="保留时间上限")
    parser.add_argument("--batch_size", type=int, default=10, help="报告进度的批次大小")

    return parser.parse_args()

def run_from_args(args):
    main(args)

if __name__ == "__main__":
    args = parse_arguments()
    main(args)
