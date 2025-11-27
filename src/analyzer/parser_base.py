import abc
import pandas as pd
from typing import Optional, Dict


class LogParser(abc.ABC):
    """
    [基类] 无人机日志解析器标准接口

    设计模式: 策略模式 (Strategy Pattern) 的基础
    作用: 规定所有具体的解析器（如 ArduParser, PX4Parser）必须具备的方法。
    """

    def __init__(self, file_path: str):
        """
        初始化解析器
        :param file_path: 日志文件的绝对或相对路径
        """
        self.file_path = file_path
        self._df: Optional[pd.DataFrame] = None
        self.metadata: Dict = {}

    @abc.abstractmethod
    def load(self) -> bool:
        """
        [抽象方法] 加载文件
        :return: 成功返回 True, 失败返回 False
        """
        pass

    @abc.abstractmethod
    def parse(self) -> pd.DataFrame:
        """
        [抽象方法] 解析数据
        :return: 标准化的 Pandas DataFrame
        """
        pass

    def get_dataframe(self) -> pd.DataFrame:
        """
        [通用方法] 获取数据的入口
        """
        if self._df is None:
            if not self.load():
                raise ValueError(f"无法加载日志文件: {self.file_path}")

            self._df = self.parse()

        return self._df