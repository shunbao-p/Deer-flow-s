# Git 使用

## 提交并上传到自己的仓库

```bash
git add .
git commit -m "本次修改说明"
git push
```

## 拉取自己仓库最新内容到本地

```bash
git pull
```

## 拉取原项目最新内容到本地

```bash
git pull upstream main
```

## 将本地覆盖为仓库中的某个历史版本

```bash
git fetch origin
git log --oneline origin/main
git reset --hard <提交号>
git clean -fd
```
