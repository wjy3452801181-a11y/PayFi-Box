const hre = require("hardhat");

const ERC20_ABI = [
  "function approve(address spender, uint256 amount) external returns (bool)",
  "function allowance(address owner, address spender) external view returns (uint256)",
];

function failFast(reason, hint) {
  console.error("Approve executor configuration error.");
  console.error(`reason: ${reason}`);
  console.error(`hint: ${hint}`);
  process.exit(1);
}

function required(name) {
  const value = process.env[name] || "";
  if (!value.trim()) {
    failFast(`missing ${name}`, `set ${name} in apps/contracts/.env`);
  }
  return value.trim();
}

async function main() {
  const tokenAddress = required("HASHKEY_PAYMENT_TOKEN_ADDRESS");
  const executorAddress = required("HASHKEY_PAYMENT_EXECUTOR_ADDRESS");
  const decimals = Number(process.env.HASHKEY_PAYMENT_TOKEN_DECIMALS || "6");
  const approveAmountHuman = process.env.HASHKEY_TOKEN_APPROVE_AMOUNT || "1000000";
  const approveAmount = hre.ethers.parseUnits(approveAmountHuman, decimals);

  const [operator] = await hre.ethers.getSigners();
  if (!operator) {
    failFast(
      "missing private key",
      "set PRIVATE_KEY or HASHKEY_OPERATOR_PRIVATE_KEY in apps/contracts/.env"
    );
  }

  console.log("Approving executor for DemoToken...");
  console.log("Operator:", operator.address);
  console.log("Token:", tokenAddress);
  console.log("Executor:", executorAddress);
  console.log("Approve amount:", approveAmountHuman);

  const token = new hre.ethers.Contract(tokenAddress, ERC20_ABI, operator);
  const tx = await token.approve(executorAddress, approveAmount);
  const receipt = await tx.wait();
  const allowance = await token.allowance(operator.address, executorAddress);

  console.log("Approve tx hash:", tx.hash);
  console.log("Allowance now:", allowance.toString());

  if (receipt && receipt.hash) {
    const explorerBase =
      process.env.HASHKEY_EXPLORER_BASE || "https://testnet-explorer.hsk.xyz";
    console.log("Approve tx explorer:", `${explorerBase.replace(/\/$/, "")}/tx/${receipt.hash}`);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
